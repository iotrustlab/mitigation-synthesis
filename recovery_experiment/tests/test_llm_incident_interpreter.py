"""Offline tests for the model-independent LLM incident boundary."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from recovery_experiment.incident_dataset import build_synthetic_incident_dataset
from recovery_experiment.incident_evidence import IncidentEvidence
from recovery_experiment.incident_interpreter import DeterministicIncidentInterpreter
from recovery_experiment.incident_pipeline import run_incident_pipeline
from recovery_experiment.llm_incident_evaluation import (
    _smoke_checks,
    _smoke_failure_layer,
    evaluate_llm_incident_interpreter,
    main as evaluation_main,
)
from recovery_experiment.llm_incident_interpreter import (
    CandidateValidationError,
    LLMIncidentInterpreter,
    candidate_response_schema,
    parse_candidate_response,
    schema_hash,
)
from recovery_experiment.openai_compatible_backend import (
    BackendResponse,
    OpenAICompatibleBackend,
    OpenAICompatibleConfig,
    StructuredOutputCompatibilityError,
)
from recovery_experiment.structured_output_schema import (
    COMPATIBLE_WITH_CLIENT_VALIDATION,
    INCOMPATIBLE,
    BackendSchemaCapabilities,
    build_serving_schema,
    capabilities_for_serving_backend,
)


class _EvidenceAwareBackend:
    def __init__(self) -> None:
        self.messages: list[tuple[dict[str, str], ...]] = []

    def complete_json(self, messages, *, schema_name, json_schema):
        copied = tuple(dict(message) for message in messages)
        self.messages.append(copied)
        evidence = IncidentEvidence.from_json(
            copied[1]["content"].split("\n", 1)[1]
        )
        candidate = DeterministicIncidentInterpreter().interpret(evidence).as_dict()
        # The legacy deterministic conflict helper intentionally leaves sources
        # blank.  A wire response must bind them to the cited records.
        for claim in candidate["fields"].values():
            if claim["conflict_evidence_ids"] and not claim["sources"]:
                claim["sources"] = ["synthetic_telemetry"]
        content = json.dumps(candidate, separators=(",", ":"))
        return BackendResponse(
            content,
            "fake-response",
            "test/model",
            "stop",
            {"prompt_tokens": 1, "completion_tokens": 1},
            0.01,
            {"id": "fake-response", "model": "test/model"},
        )


def _wire_document(case_index: int = 0) -> tuple[object, dict[str, object]]:
    case = build_synthetic_incident_dataset().cases[case_index]
    candidate = DeterministicIncidentInterpreter().interpret(case.evidence)
    return case, candidate.as_dict()


class LLMIncidentInterpreterTests(unittest.TestCase):
    def test_valid_structured_response_runs_unchanged_pipeline(self) -> None:
        case, document = _wire_document()
        candidate = parse_candidate_response(json.dumps(document), case.evidence)
        result = run_incident_pipeline(
            case.evidence,
            case.trusted_plant_knowledge,
            case.recovery_configuration,
            interpreter=type("Fixed", (), {"interpret": lambda self, evidence: candidate})(),
        )
        self.assertTrue(result.grounding.succeeded)
        self.assertIsNotNone(result.formal_assessment)
        self.assertFalse(result.online_prover_invoked)

    def test_fabricated_and_field_mismatched_ids_are_rejected(self) -> None:
        case, document = _wire_document()
        document["fields"]["x1"]["evidence_ids"] = ["invented:evidence"]
        with self.assertRaisesRegex(CandidateValidationError, "fabricated"):
            parse_candidate_response(json.dumps(document), case.evidence)

        case, document = _wire_document()
        document["fields"]["x1"]["evidence_ids"] = [
            f"{case.scenario_id}:observation:x2"
        ]
        with self.assertRaisesRegex(CandidateValidationError, "do not support"):
            parse_candidate_response(json.dumps(document), case.evidence)

    def test_source_spoofing_and_trusted_status_are_rejected(self) -> None:
        case, document = _wire_document()
        document["fields"]["x1"]["sources"] = ["synthetic_ids"]
        with self.assertRaisesRegex(CandidateValidationError, "sources do not exactly match"):
            parse_candidate_response(json.dumps(document), case.evidence)

        case, document = _wire_document()
        document["fields"]["x1"]["status"] = "GROUNDED"
        with self.assertRaisesRegex(
            CandidateValidationError,
            "canonical CandidateRecoveryContext schema validation failed",
        ):
            parse_candidate_response(json.dumps(document), case.evidence)

    def test_real_id_cannot_be_used_to_change_observed_value(self) -> None:
        case, document = _wire_document()
        document["fields"]["x1"]["value"] = 6.25
        with self.assertRaisesRegex(CandidateValidationError, "latest observation"):
            parse_candidate_response(json.dumps(document), case.evidence)

    def test_interpreter_preserves_invalid_raw_response(self) -> None:
        case, document = _wire_document()
        document["fields"]["x1"]["evidence_ids"] = ["invented:evidence"]

        class InvalidBackend:
            def complete_json(self, messages, *, schema_name, json_schema):
                return BackendResponse(
                    json.dumps(document), "bad", "test/model", "stop", {}, 0.1, {}
                )

        with self.assertRaises(CandidateValidationError) as caught:
            LLMIncidentInterpreter(InvalidBackend()).interpret_with_trace(case.evidence)
        self.assertIsNotNone(caught.exception.backend_response)
        self.assertIn("invented:evidence", caught.exception.backend_response.content)

    def test_canonical_schema_rejects_duplicate_before_pipeline(self) -> None:
        case, document = _wire_document()
        evidence_ids = document["fields"]["x1"]["evidence_ids"]
        self.assertTrue(evidence_ids)
        evidence_ids.append(evidence_ids[0])

        class DuplicateBackend:
            def complete_json(self, messages, *, schema_name, json_schema):
                return BackendResponse(
                    json.dumps(document), "duplicate", "test/model", "stop", {}, 0.1, {}
                )

        with patch(
            "recovery_experiment.llm_incident_evaluation.run_incident_pipeline"
        ) as pipeline:
            result = evaluate_llm_incident_interpreter(
                LLMIncidentInterpreter(DuplicateBackend()), cases=(case,)
            )
        pipeline.assert_not_called()
        outcome = result.outcomes[0]
        self.assertEqual(outcome.error_type, "CandidateValidationError")
        self.assertIn(
            "canonical CandidateRecoveryContext schema validation failed",
            outcome.error_message,
        )
        self.assertIn("non-unique", outcome.error_message)
        self.assertIsNone(outcome.candidate)
        self.assertIsNone(outcome.pipeline)
        self.assertEqual(outcome.as_dict()["validation"]["canonical_schema"], "FAIL")
        self.assertEqual(
            outcome.as_dict()["validation"]["provenance_and_binding"], "NOT_RUN"
        )

    def test_nonfinite_json_is_classified_as_invalid_json(self) -> None:
        case, document = _wire_document()
        document["fields"]["x1"]["value"] = float("nan")

        class NonfiniteBackend:
            def complete_json(self, messages, *, schema_name, json_schema):
                return BackendResponse(
                    json.dumps(document), "nonfinite", "test/model", "stop", {}, 0.1, {}
                )

        with patch(
            "recovery_experiment.llm_incident_evaluation.run_incident_pipeline"
        ) as pipeline:
            result = evaluate_llm_incident_interpreter(
                LLMIncidentInterpreter(NonfiniteBackend()), cases=(case,)
            )
        pipeline.assert_not_called()
        outcome = result.outcomes[0]
        checks = _smoke_checks(outcome)
        self.assertIn("model response is not JSON", outcome.error_message)
        self.assertEqual(
            _smoke_failure_layer(outcome, checks), "MODEL_OUTPUT_INVALID_JSON"
        )
        self.assertEqual(outcome.as_dict()["validation"]["canonical_schema"], "NOT_RUN")

    def test_provenance_failure_preserves_canonical_pass_stage(self) -> None:
        case, document = _wire_document()
        document["fields"]["plant_identity"]["evidence_ids"] = [
            "incident_metadata:plant_identity"
        ]

        class FabricatedBackend:
            def complete_json(self, messages, *, schema_name, json_schema):
                return BackendResponse(
                    json.dumps(document), "fabricated", "test/model", "stop", {}, 0.1, {}
                )

        with patch(
            "recovery_experiment.llm_incident_evaluation.run_incident_pipeline"
        ) as pipeline:
            result = evaluate_llm_incident_interpreter(
                LLMIncidentInterpreter(FabricatedBackend()), cases=(case,)
            )
        pipeline.assert_not_called()
        outcome = result.outcomes[0]
        checks = _smoke_checks(outcome)
        self.assertTrue(checks["response_parsed"])
        self.assertTrue(checks["canonical_schema_valid"])
        self.assertFalse(checks["provenance_valid"])
        self.assertTrue(checks["online_cleo_not_invoked"])
        self.assertEqual(_smoke_failure_layer(outcome, checks), "PROVENANCE_FAILURE")
        self.assertEqual(outcome.as_dict()["validation"]["canonical_schema"], "PASS")
        self.assertEqual(
            outcome.as_dict()["validation"]["provenance_and_binding"], "FAIL"
        )

    def test_fake_oracle_exercises_all_27_without_cleo(self) -> None:
        backend = _EvidenceAwareBackend()
        result = evaluate_llm_incident_interpreter(LLMIncidentInterpreter(backend))
        self.assertEqual(result.requested_case_count, 27)
        self.assertEqual(result.metrics["case_failures"], 0)
        self.assertEqual(
            result.metrics["grounding"]["status_accuracy"]["accuracy"], 1.0
        )
        self.assertEqual(
            result.metrics["formal_consequences"]["final_recovery_decision"]["accuracy"],
            1.0,
        )
        self.assertTrue(
            all(
                outcome.pipeline is not None
                and not outcome.pipeline.online_prover_invoked
                for outcome in result.outcomes
            )
        )
        prompt = backend.messages[0][0]["content"]
        for forbidden in (
            "flowing_backup_takeover",
            "COVERED_BY_CERTIFICATE",
            "selected_policy",
            "gold scenario",
        ):
            self.assertNotIn(forbidden, prompt)


class OpenAICompatibleBackendTests(unittest.TestCase):
    def test_canonical_schema_is_unchanged_and_retains_unique_items(self) -> None:
        schema = candidate_response_schema()
        paths: list[str] = []

        def visit(value: object, path: str = "$") -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    child_path = f"{path}.{key}"
                    if key == "uniqueItems":
                        self.assertIs(child, True)
                        paths.append(child_path)
                    visit(child, child_path)
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    visit(child, f"{path}[{index}]")

        visit(schema)
        self.assertEqual(len(paths), 64)
        self.assertEqual(
            schema_hash(schema),
            "7b5237458e64d0aa6b26dbf954a2c4829aae499ba72aeaf33952ec2869fd0e5a",
        )

    def test_serving_schema_transformation_is_recursive_and_nonmutating(self) -> None:
        canonical = {
            "type": "object",
            "properties": {
                "values": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": {
                        "type": "array",
                        "uniqueItems": True,
                        "items": {"type": "string"},
                    },
                },
                "choice": {
                    "anyOf": [
                        {
                            "type": "array",
                            "uniqueItems": True,
                            "items": {"type": "number"},
                        },
                        {"type": "null"},
                    ]
                },
                # This is an instance property name, not a schema keyword.
                "uniqueItems": {"type": "boolean"},
            },
            "required": ["values", "choice", "uniqueItems"],
            "additionalProperties": False,
        }
        snapshot = copy.deepcopy(canonical)
        plan = build_serving_schema(
            canonical,
            capabilities_for_serving_backend("vllm-auto", backend_version="0.27.0"),
        )
        self.assertEqual(canonical, snapshot)
        self.assertIsNot(plan.serving_schema, canonical)
        self.assertEqual(plan.status, COMPATIBLE_WITH_CLIENT_VALIDATION)
        self.assertEqual(len(plan.removed_generation_constraints), 3)
        self.assertEqual(
            {item.keyword for item in plan.removed_generation_constraints},
            {"uniqueItems"},
        )
        values = plan.serving_schema["properties"]["values"]
        self.assertNotIn("uniqueItems", values)
        self.assertEqual(values["minItems"], 1)
        self.assertNotIn("uniqueItems", values["items"])
        self.assertIn("uniqueItems", plan.serving_schema["properties"])
        self.assertEqual(
            plan.serving_schema["properties"]["uniqueItems"], {"type": "boolean"}
        )
        choice = plan.serving_schema["properties"]["choice"]
        self.assertNotIn("uniqueItems", choice["anyOf"][0])

    def test_candidate_serving_plan_removes_only_64_reviewed_constraints(self) -> None:
        canonical = candidate_response_schema()
        snapshot = copy.deepcopy(canonical)
        plan = build_serving_schema(
            canonical, capabilities_for_serving_backend("vllm-auto")
        )
        self.assertEqual(canonical, snapshot)
        self.assertEqual(len(plan.removed_generation_constraints), 64)
        self.assertEqual(plan.unsupported_unhandled_constraints, ())
        self.assertEqual(
            plan.serving_schema_hash,
            "3680129007e01223a2b6f2d6eba73d834316434ea04356393c4924535d5bd0e1",
        )

    def test_adapter_does_not_strip_unreported_keywords(self) -> None:
        canonical = {
            "type": "array",
            "uniqueItems": True,
            "items": {"type": "string"},
        }
        plan = build_serving_schema(
            canonical, BackendSchemaCapabilities("full JSON Schema")
        )
        self.assertEqual(plan.serving_schema, canonical)
        self.assertIsNot(plan.serving_schema, canonical)
        self.assertEqual(plan.canonical_schema_hash, plan.serving_schema_hash)
        self.assertEqual(plan.removed_generation_constraints, ())

    def test_unknown_unsupported_constraint_fails_before_http(self) -> None:
        capabilities = BackendSchemaCapabilities(
            "test backend", frozenset({"contains"}), "1.0"
        )
        schema = {
            "type": "array",
            "contains": {"type": "string"},
            "minItems": 1,
        }
        plan = build_serving_schema(schema, capabilities)
        self.assertEqual(plan.status, INCOMPATIBLE)
        self.assertEqual(
            [(item.path, item.keyword) for item in plan.unsupported_unhandled_constraints],
            [("$", "contains")],
        )
        backend = OpenAICompatibleBackend(
            OpenAICompatibleConfig("http://127.0.0.1:9999/v1", "test/model"),
            schema_capabilities=capabilities,
        )
        with patch(
            "recovery_experiment.openai_compatible_backend.urllib.request.urlopen"
        ) as opened:
            with self.assertRaises(StructuredOutputCompatibilityError):
                backend.complete_json(
                    ({"role": "user", "content": "evidence"},),
                    schema_name="candidate",
                    json_schema=schema,
                )
        opened.assert_not_called()

    def test_structured_payload_and_public_metadata(self) -> None:
        class FakeHTTPResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(
                    {
                        "id": "r1",
                        "model": "another/model",
                        "choices": [
                            {
                                "message": {"content": "{}"},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {},
                    }
                ).encode()

        config = OpenAICompatibleConfig(
            "http://127.0.0.1:9999/v1",
            "another/model",
            api_key="secret-value",
        )
        backend = OpenAICompatibleBackend(
            config,
            schema_capabilities=capabilities_for_serving_backend(
                "vllm-auto", backend_version="0.27.0"
            ),
        )
        with patch(
            "recovery_experiment.openai_compatible_backend.urllib.request.urlopen",
            return_value=FakeHTTPResponse(),
        ) as opened:
            response = backend.complete_json(
                ({"role": "user", "content": "evidence"},),
                schema_name="candidate",
                json_schema={
                    "type": "array",
                    "uniqueItems": True,
                    "minItems": 1,
                    "items": {"type": "string"},
                },
            )
        request = opened.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "another/model")
        self.assertEqual(payload["temperature"], 0.0)
        self.assertEqual(payload["seed"], 20260926)
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        sent_schema = payload["response_format"]["json_schema"]["schema"]
        self.assertNotIn("uniqueItems", sent_schema)
        self.assertEqual(sent_schema["minItems"], 1)
        self.assertFalse(payload["chat_template_kwargs"]["enable_thinking"])
        self.assertEqual(
            response.schema_compatibility["status"],
            COMPATIBLE_WITH_CLIENT_VALIDATION,
        )
        self.assertNotIn("secret-value", json.dumps(config.public_dict()))
        self.assertNotIn("secret-value", repr(config))


class EvaluationCLITests(unittest.TestCase):
    def test_smoke_artifact_is_complete_and_never_overwritten(self) -> None:
        backend = _EvidenceAwareBackend()
        backend.list_models = lambda: {"data": [{"id": "test/model"}]}
        backend.server_version = lambda: {"version": "test"}
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "smoke"
            arguments = [
                "smoke",
                "--model",
                "test/model",
                "--revision",
                "test-revision",
                "--output-dir",
                str(output),
                "--serving-backend",
                "vllm-auto",
            ]
            with (
                patch(
                    "recovery_experiment.llm_incident_evaluation.OpenAICompatibleBackend",
                    return_value=backend,
                ),
                patch(
                    "recovery_experiment.llm_incident_evaluation._gpu_metadata",
                    return_value={
                        "gpu_model": "test GPU",
                        "gpu_count": 1,
                        "source": "test",
                    },
                ),
                patch("builtins.print"),
            ):
                self.assertEqual(evaluation_main(arguments), 0)
                with self.assertRaisesRegex(SystemExit, "refusing to overwrite"):
                    evaluation_main(arguments)
            self.assertTrue((output / "manifest.json").is_file())
            self.assertTrue((output / "completion.json").is_file())
            completion = json.loads(
                (output / "completion.json").read_text(encoding="utf-8")
            )
            manifest = json.loads(
                (output / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(completion["status"], "PASS")
            self.assertTrue(all(completion["smoke_checks"].values()))
            case_record = json.loads(
                next((output / "cases").iterdir()).read_text(encoding="utf-8")
            )
            self.assertEqual(case_record["validation"]["canonical_schema"], "PASS")
            self.assertEqual(
                case_record["validation"]["provenance_and_binding"], "PASS"
            )
            self.assertEqual(
                manifest["interpreter"]["candidate_schema_version"],
                "candidate-recovery-context-v1",
            )
            structured = manifest["structured_output"]
            self.assertEqual(
                structured["canonical_schema_hash"],
                "7b5237458e64d0aa6b26dbf954a2c4829aae499ba72aeaf33952ec2869fd0e5a",
            )
            self.assertEqual(
                structured["serving_schema_hash"],
                "3680129007e01223a2b6f2d6eba73d834316434ea04356393c4924535d5bd0e1",
            )
            self.assertEqual(structured["serving_backend_version"], "test")
            self.assertEqual(structured["removed_generation_constraint_count"], 64)


if __name__ == "__main__":
    unittest.main()
