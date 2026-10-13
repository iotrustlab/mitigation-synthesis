"""Reproducible smoke and baseline evaluation for an external LLM interpreter.

The evaluator sends only ``IncidentEvidence`` to the interpreter.  Gold labels
are read after inference and are used solely for offline scoring.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
import time
from typing import Callable, Mapping, Sequence

from .candidate_context import CandidateRecoveryContext
from .context_grounding import GroundingStatus
from .incident_dataset import (
    SyntheticIncidentCase,
    SyntheticIncidentDataset,
    build_synthetic_incident_dataset,
)
from .incident_evidence_evaluation import (
    CaseEvaluation,
    evaluate_incident_pipeline_result,
)
from .incident_pipeline import IncidentPipelineResult, run_incident_pipeline
from .llm_incident_interpreter import (
    CandidateProvenanceAudit,
    CandidateValidationError,
    LLMIncidentInterpreter,
    LLMInterpretation,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    audit_candidate_provenance,
    candidate_response_schema,
    prompt_contract_hash,
)
from .openai_compatible_backend import (
    BackendError,
    BackendResponse,
    OpenAICompatibleBackend,
    OpenAICompatibleConfig,
)
from .structured_output_schema import (
    INCOMPATIBLE,
    build_serving_schema,
    capabilities_for_serving_backend,
)


OFFICIAL_QWEN_MODEL = "Qwen/Qwen3.5-9B"
OFFICIAL_QWEN_REVISION = "c202236235762e1c871ad0ccb60c8ee5ba337b9a"
BASELINE_NAME = "QWEN_BASELINE_V1"
SMOKE_NAME = "QWEN_SMOKE_V1"

INTERPRETATION_GROUPS: Mapping[str, tuple[str, ...]] = {
    "compromised_component": ("suspected_compromised_component",),
    "attacker_capability": ("attacker_capability",),
    "physical_state": ("x1", "x2", "p1_command", "p1_actual_state"),
    "resource_observation": (
        "backup_operational",
        "isolation_operational",
        "inflow_control_operational",
        "demand_control_operational",
    ),
    "timing": (
        "control_period",
        "isolation_delay",
        "backup_startup_delay",
        "attacker_command_schedule",
    ),
}


@dataclass(frozen=True)
class _FixedCandidateInterpreter:
    candidate: CandidateRecoveryContext

    def interpret(self, _evidence: object) -> CandidateRecoveryContext:
        return self.candidate


@dataclass(frozen=True)
class LLMCaseOutcome:
    case: SyntheticIncidentCase
    trace: LLMInterpretation | None
    backend_response: BackendResponse | None
    candidate: CandidateRecoveryContext | None
    provenance: CandidateProvenanceAudit
    pipeline: IncidentPipelineResult | None
    comparison: CaseEvaluation | None
    interpretation_matches: tuple[tuple[str, bool], ...]
    error_type: str | None
    error_message: str | None
    elapsed_seconds: float

    def as_dict(self) -> dict[str, object]:
        canonical_status, provenance_status = _validation_statuses(self)
        return {
            "scenario_id": self.case.scenario_id,
            "family": self.case.family,
            "evidence_sha256": hashlib.sha256(
                self.case.evidence.to_json().encode("utf-8")
            ).hexdigest(),
            "trace": None if self.trace is None else self.trace.as_dict(),
            "backend_response": (
                None
                if self.trace is not None or self.backend_response is None
                else self.backend_response.as_dict()
            ),
            "candidate": None if self.candidate is None else self.candidate.as_dict(),
            "validation": {
                "canonical_schema": canonical_status,
                "provenance_and_binding": provenance_status,
            },
            "provenance": self.provenance.as_dict(),
            "pipeline": None if self.pipeline is None else self.pipeline.as_dict(),
            "evaluation": None if self.comparison is None else self.comparison.as_dict(),
            "interpretation_matches": dict(self.interpretation_matches),
            "error": (
                None
                if self.error_type is None
                else {"type": self.error_type, "message": self.error_message}
            ),
            "elapsed_seconds": self.elapsed_seconds,
        }


def _validation_statuses(outcome: LLMCaseOutcome) -> tuple[str, str]:
    message = outcome.error_message or ""
    canonical_failed = (
        outcome.error_type == "CandidateValidationError"
        and "canonical CandidateRecoveryContext schema" in message
    )
    invalid_json = (
        outcome.error_type == "CandidateValidationError"
        and "model response is not JSON" in message
    )
    canonical_status = (
        "PASS"
        if outcome.candidate is not None
        else "FAIL"
        if canonical_failed
        else "PASS"
        if outcome.backend_response is not None
        and outcome.error_type == "CandidateValidationError"
        and not invalid_json
        else "NOT_RUN"
    )
    provenance_status = (
        "PASS"
        if outcome.candidate is not None
        and not outcome.provenance.fabricated_ids
        and not outcome.provenance.missing_support_claims
        and not outcome.provenance.unsupported_claims
        else "NOT_RUN"
        if canonical_status != "PASS"
        else "FAIL"
    )
    return canonical_status, provenance_status


@dataclass(frozen=True)
class LLMEvaluationResult:
    dataset_seed: int
    requested_case_count: int
    outcomes: tuple[LLMCaseOutcome, ...]
    metrics: Mapping[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "dataset_seed": self.dataset_seed,
            "requested_case_count": self.requested_case_count,
            "completed_case_count": len(self.outcomes),
            "metrics": dict(self.metrics),
            "cases": [outcome.as_dict() for outcome in self.outcomes],
        }


def evaluate_llm_incident_interpreter(
    interpreter: LLMIncidentInterpreter,
    dataset: SyntheticIncidentDataset | None = None,
    *,
    cases: Sequence[SyntheticIncidentCase] | None = None,
    case_callback: Callable[[LLMCaseOutcome], None] | None = None,
) -> LLMEvaluationResult:
    """Run each selected first attempt once, then score it against held-out gold."""

    dataset = dataset or build_synthetic_incident_dataset()
    selected = tuple(dataset.cases if cases is None else cases)
    outcomes: list[LLMCaseOutcome] = []
    for case in selected:
        outcome = _evaluate_case(interpreter, case)
        outcomes.append(outcome)
        if case_callback is not None:
            case_callback(outcome)
    frozen = tuple(outcomes)
    return LLMEvaluationResult(
        dataset.seed,
        len(selected),
        frozen,
        _aggregate_metrics(frozen),
    )


def _evaluate_case(
    interpreter: LLMIncidentInterpreter, case: SyntheticIncidentCase
) -> LLMCaseOutcome:
    started = time.perf_counter()
    trace: LLMInterpretation | None = None
    response: BackendResponse | None = None
    candidate: CandidateRecoveryContext | None = None
    pipeline: IncidentPipelineResult | None = None
    comparison: CaseEvaluation | None = None
    error_type: str | None = None
    error_message: str | None = None
    provenance = CandidateProvenanceAudit(0, 0, (), (), ())
    try:
        trace = interpreter.interpret_with_trace(case.evidence)
        response = trace.backend_response
        candidate = trace.candidate
        provenance = audit_candidate_provenance(response.content, case.evidence)
        pipeline = run_incident_pipeline(
            case.evidence,
            case.trusted_plant_knowledge,
            case.recovery_configuration,
            interpreter=_FixedCandidateInterpreter(candidate),
        )
        comparison = evaluate_incident_pipeline_result(case, pipeline)
    except CandidateValidationError as exc:
        response = exc.backend_response
        if response is not None:
            provenance = audit_candidate_provenance(response.content, case.evidence)
        if (
            not provenance.fabricated_ids
            and not provenance.missing_support_claims
            and not provenance.unsupported_claims
        ):
            provenance = CandidateProvenanceAudit(
                provenance.total_references,
                provenance.valid_references,
                provenance.fabricated_ids,
                provenance.missing_support_claims,
                ("strict_validation_failure",),
            )
        error_type = type(exc).__name__
        error_message = str(exc)
    except BackendError as exc:
        error_type = type(exc).__name__
        error_message = str(exc)
    except Exception as exc:  # Preserve an unexpected first-attempt failure in the run artifact.
        error_type = type(exc).__name__
        error_message = str(exc)

    matches = _interpretation_matches(case, candidate)
    return LLMCaseOutcome(
        case,
        trace,
        response,
        candidate,
        provenance,
        pipeline,
        comparison,
        matches,
        error_type,
        error_message,
        time.perf_counter() - started,
    )


def _interpretation_matches(
    case: SyntheticIncidentCase,
    candidate: CandidateRecoveryContext | None,
) -> tuple[tuple[str, bool], ...]:
    gold = case.ground_truth_candidate.fields()
    actual = None if candidate is None else candidate.fields()
    names = tuple(name for group in INTERPRETATION_GROUPS.values() for name in group)
    return tuple(
        (
            name,
            actual is not None
            and actual[name].status is gold[name].status
            and _normalized(actual[name].value) == _normalized(gold[name].value),
        )
        for name in names
    )


def _normalized(value: object) -> object:
    if isinstance(value, tuple):
        return tuple(_normalized(item) for item in value)
    enum_value = getattr(value, "value", None)
    return enum_value if isinstance(enum_value, str) else value


def _accuracy(correct: int, total: int) -> dict[str, object]:
    return {
        "correct": correct,
        "total": total,
        "accuracy": 1.0 if total == 0 else correct / total,
    }


def _aggregate_metrics(outcomes: tuple[LLMCaseOutcome, ...]) -> dict[str, object]:
    per_field: dict[str, dict[str, object]] = {}
    match_maps = [dict(outcome.interpretation_matches) for outcome in outcomes]
    for name in tuple(name for group in INTERPRETATION_GROUPS.values() for name in group):
        per_field[name] = _accuracy(
            sum(matches.get(name, False) for matches in match_maps), len(outcomes)
        )
    categories = {
        category: _accuracy(
            sum(
                matches.get(name, False)
                for matches in match_maps
                for name in names
            ),
            len(outcomes) * len(names),
        )
        for category, names in INTERPRETATION_GROUPS.items()
    }

    expected_acceptance = [
        outcome.case.gold.grounding_status is GroundingStatus.GROUNDED_CONTEXT
        for outcome in outcomes
    ]
    actual_acceptance = [
        outcome.pipeline is not None and outcome.pipeline.grounding.succeeded
        for outcome in outcomes
    ]
    grounding = {
        "correct_acceptance": sum(
            expected and actual
            for expected, actual in zip(expected_acceptance, actual_acceptance)
        ),
        "correct_rejection": sum(
            not expected and not actual
            for expected, actual in zip(expected_acceptance, actual_acceptance)
        ),
        "false_acceptance": sum(
            not expected and actual
            for expected, actual in zip(expected_acceptance, actual_acceptance)
        ),
        "false_rejection": sum(
            expected and not actual
            for expected, actual in zip(expected_acceptance, actual_acceptance)
        ),
        "grounding_not_executed": sum(
            outcome.pipeline is None for outcome in outcomes
        ),
        "classification_definition": (
            "end-to-end accepted versus not accepted; pre-grounding validation "
            "failures count as rejection and are also reported as not executed"
        ),
    }
    grounding["status_accuracy"] = _accuracy(
        grounding["correct_acceptance"] + grounding["correct_rejection"],
        len(outcomes),
    )

    gold_grounded = [
        outcome
        for outcome in outcomes
        if outcome.case.gold.grounding_status is GroundingStatus.GROUNDED_CONTEXT
    ]
    formal_metrics = {
        "recovery_template": _outcome_accuracy(gold_grounded, "template_match"),
        "formal_model": _outcome_accuracy(gold_grounded, "formal_model_match"),
        "certificate": _outcome_accuracy(gold_grounded, "certificate_match"),
        "service_contract": _outcome_accuracy(gold_grounded, "service_match"),
        "final_recovery_decision": _outcome_accuracy(
            gold_grounded, "selection_match"
        ),
        "denominator_definition": "all gold-grounded cases, including LLM/schema failures",
    }

    total_references = sum(outcome.provenance.total_references for outcome in outcomes)
    valid_references = sum(outcome.provenance.valid_references for outcome in outcomes)
    fabricated = sorted(
        {
            item
            for outcome in outcomes
            for item in outcome.provenance.fabricated_ids
        }
    )
    provenance = {
        "valid_evidence_references": _accuracy(valid_references, total_references),
        "fabricated_evidence_ids": fabricated,
        "fabricated_evidence_id_count": len(fabricated),
        "fabricated_reference_occurrences": sum(
            len(outcome.provenance.fabricated_ids) for outcome in outcomes
        ),
        "cases_with_fabricated_ids": sum(
            bool(outcome.provenance.fabricated_ids) for outcome in outcomes
        ),
        "missing_supporting_evidence_claims": sum(
            len(outcome.provenance.missing_support_claims) for outcome in outcomes
        ),
        "cases_with_missing_support": sum(
            bool(outcome.provenance.missing_support_claims) for outcome in outcomes
        ),
        "unsupported_claims": sum(
            len(outcome.provenance.unsupported_claims) for outcome in outcomes
        ),
        "cases_with_unsupported_claims": sum(
            bool(outcome.provenance.unsupported_claims) for outcome in outcomes
        ),
        "strict_validation_failures": sum(
            outcome.error_type == "CandidateValidationError" for outcome in outcomes
        ),
    }

    consequences = {
        "interpretation_error_no_downstream_effect": 0,
        "blocked_by_schema_or_reference_validation": 0,
        "rejected_by_grounding": 0,
        "changed_recovery_template": 0,
        "changed_formal_problem": 0,
        "changed_certificate_applicability": 0,
        "changed_final_recovery_decision": 0,
    }
    for outcome in outcomes:
        interpretation_error = any(
            not match for _, match in outcome.interpretation_matches
        )
        if not interpretation_error:
            continue
        if outcome.error_type == "CandidateValidationError":
            consequences["blocked_by_schema_or_reference_validation"] += 1
        if outcome.pipeline is not None and not outcome.pipeline.grounding.succeeded:
            consequences["rejected_by_grounding"] += 1
        template_changed, formal_changed, certificate_changed, final_changed = (
            _downstream_changes(outcome)
        )
        consequences["changed_recovery_template"] += template_changed
        consequences["changed_formal_problem"] += formal_changed
        consequences["changed_certificate_applicability"] += certificate_changed
        consequences["changed_final_recovery_decision"] += final_changed
        if (
            outcome.pipeline is not None
            and outcome.pipeline.grounding.succeeded
            == (
                outcome.case.gold.grounding_status
                is GroundingStatus.GROUNDED_CONTEXT
            )
            and not any(
                (template_changed, formal_changed, certificate_changed, final_changed)
            )
        ):
            consequences["interpretation_error_no_downstream_effect"] += 1

    return {
        "interpretation": {
            "match_definition": "exact candidate status and normalized value",
            "categories": categories,
            "fields": per_field,
        },
        "provenance": provenance,
        "grounding": grounding,
        "formal_consequences": formal_metrics,
        "error_propagation_nonexclusive": consequences,
        "case_failures": sum(outcome.error_type is not None for outcome in outcomes),
    }


def _outcome_accuracy(
    outcomes: Sequence[LLMCaseOutcome], attribute: str
) -> dict[str, object]:
    return _accuracy(
        sum(
            outcome.comparison is not None
            and getattr(outcome.comparison, attribute) is True
            for outcome in outcomes
        ),
        len(outcomes),
    )


def _downstream_changes(outcome: LLMCaseOutcome) -> tuple[bool, bool, bool, bool]:
    case = outcome.case
    pipeline = outcome.pipeline
    if pipeline is None or pipeline.formal_assessment is None:
        templates: tuple[str, ...] = ()
        models: tuple[tuple[str, str | None], ...] = ()
        certificates: tuple[tuple[str, str | None], ...] = ()
    else:
        applicable = tuple(
            item
            for item in pipeline.formal_assessment.templates
            if item.applicability.applicable
        )
        templates = tuple(item.template_id.value for item in applicable)
        models = tuple(
            (
                item.template_id.value,
                None if item.construction is None else item.construction.formal_model_id,
            )
            for item in applicable
        )
        certificates = tuple(
            (
                item.template_id.value,
                None if item.certificate is None else item.certificate.status.value,
            )
            for item in applicable
        )
    actual_decision = (
        None
        if pipeline is None or pipeline.selection is None
        else (pipeline.selection.status.value, pipeline.selection.selected_policy)
    )
    expected_decision = (
        None
        if case.gold.selection_status is None
        else (case.gold.selection_status, case.gold.selected_policy)
    )
    return (
        templates != case.gold.applicable_templates,
        models != case.gold.formal_models,
        certificates != case.gold.certificate_statuses,
        actual_decision != expected_decision,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "smoke", "baseline"))
    parser.add_argument(
        "--base-url",
        default=os.environ.get("DRICS_LLM_BASE_URL", "http://127.0.0.1:8000/v1"),
    )
    parser.add_argument(
        "--model", default=os.environ.get("DRICS_LLM_MODEL", OFFICIAL_QWEN_MODEL)
    )
    parser.add_argument(
        "--revision",
        default=os.environ.get("DRICS_LLM_REVISION", OFFICIAL_QWEN_REVISION),
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--timeout",
        type=float,
        default=_env_float("DRICS_LLM_TIMEOUT_SECONDS", 180.0),
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=_env_float("DRICS_LLM_TEMPERATURE", 0.0),
    )
    parser.add_argument(
        "--top-p", type=float, default=_env_float("DRICS_LLM_TOP_P", 1.0)
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=_env_int("DRICS_LLM_MAX_OUTPUT_TOKENS", 4096),
    )
    parser.add_argument(
        "--seed", type=int, default=_env_int("DRICS_LLM_SEED", 20260926)
    )
    parser.add_argument(
        "--chat-template-disable-thinking",
        action=argparse.BooleanOptionalAction,
        default=_env_bool("DRICS_LLM_DISABLE_THINKING", True),
        help=(
            "send enable_thinking=false; use --no-chat-template-disable-thinking "
            "for a backend that lacks this parameter"
        ),
    )
    parser.add_argument("--smoke-case", default="A-immediate-nominal-1")
    parser.add_argument(
        "--gpu-model", default=os.environ.get("DRICS_LLM_GPU_MODEL")
    )
    parser.add_argument(
        "--gpu-count", type=int, default=_optional_int(os.environ.get("DRICS_LLM_GPU_COUNT"))
    )
    parser.add_argument(
        "--quantization", default=os.environ.get("DRICS_LLM_QUANTIZATION", "none")
    )
    parser.add_argument(
        "--dtype", default=os.environ.get("DRICS_LLM_DTYPE", "bfloat16")
    )
    parser.add_argument(
        "--served-max-model-len",
        type=int,
        default=_env_int("DRICS_LLM_MAX_MODEL_LEN", 16384),
    )
    parser.add_argument(
        "--tensor-parallel-size",
        type=int,
        default=_env_int("DRICS_LLM_TENSOR_PARALLEL_SIZE", 1),
    )
    parser.add_argument(
        "--model-manifest",
        type=Path,
        default=_optional_path(os.environ.get("DRICS_LLM_MODEL_MANIFEST")),
    )
    parser.add_argument(
        "--serving-backend",
        default=os.environ.get("DRICS_LLM_SERVING_BACKEND", "canonical"),
        help="reviewed serving-schema capability profile: canonical or vllm-auto",
    )
    parser.add_argument(
        "--serving-backend-version",
        default=os.environ.get("DRICS_LLM_SERVING_BACKEND_VERSION"),
        help="optional version for a local-only preflight; live runs use /version",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    canonical_schema = candidate_response_schema()
    try:
        local_capabilities = capabilities_for_serving_backend(
            args.serving_backend,
            backend_version=args.serving_backend_version,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    local_schema_plan = build_serving_schema(
        canonical_schema, local_capabilities
    )
    if local_schema_plan.status == INCOMPATIBLE:
        raise SystemExit(
            "structured-output schema preflight failed before contacting the LLM: "
            + json.dumps(local_schema_plan.report_dict(), sort_keys=True)
        )
    if args.mode == "preflight":
        print(json.dumps(local_schema_plan.report_dict(), indent=2, sort_keys=True))
        return 0

    config = OpenAICompatibleConfig(
        base_url=args.base_url,
        model=args.model,
        api_key=os.environ.get("DRICS_LLM_API_KEY"),
        timeout_seconds=args.timeout,
        temperature=args.temperature,
        top_p=args.top_p,
        max_output_tokens=args.max_output_tokens,
        seed=args.seed,
        disable_thinking=args.chat_template_disable_thinking,
    )
    discovery_backend = OpenAICompatibleBackend(
        config, schema_capabilities=local_capabilities
    )
    try:
        models = discovery_backend.list_models()
    except BackendError as exc:
        raise SystemExit(f"LLM server preflight failed: {exc}") from exc
    served_ids = _served_model_ids(models)
    if config.model not in served_ids:
        raise SystemExit(
            f"configured model {config.model!r} is not served; available={served_ids}"
        )
    version = discovery_backend.server_version()
    if args.model == OFFICIAL_QWEN_MODEL:
        _validate_vllm_version(version)
    backend_version = (
        version.get("version")
        if isinstance(version, Mapping) and isinstance(version.get("version"), str)
        else args.serving_backend_version
    )
    serving_capabilities = capabilities_for_serving_backend(
        args.serving_backend, backend_version=backend_version
    )
    schema_plan = build_serving_schema(canonical_schema, serving_capabilities)
    if schema_plan.status == INCOMPATIBLE:
        raise SystemExit(
            "structured-output schema preflight became incompatible: "
            + json.dumps(schema_plan.report_dict(), sort_keys=True)
        )
    backend = OpenAICompatibleBackend(
        config, schema_capabilities=serving_capabilities
    )

    manifest_path = _resolve_model_manifest_path(
        args.model_manifest, args.model, args.revision
    )
    model_manifest = _load_model_manifest(manifest_path)
    if args.model == OFFICIAL_QWEN_MODEL:
        if model_manifest is None:
            raise SystemExit(
                "the official Qwen run requires its downloaded DRICS_MODEL_MANIFEST.json"
            )
        _validate_official_model_manifest(model_manifest, args.revision)

    dataset = build_synthetic_incident_dataset()
    if args.mode == "smoke":
        selected = tuple(
            case for case in dataset.cases if case.scenario_id == args.smoke_case
        )
        if len(selected) != 1:
            raise SystemExit(f"unknown smoke case: {args.smoke_case}")
    else:
        selected = dataset.cases

    output_dir = args.output_dir or (
        Path(__file__).resolve().parent
        / "results"
        / "llm"
        / (SMOKE_NAME if args.mode == "smoke" else BASELINE_NAME)
    )
    if (
        args.mode == "baseline"
        and args.output_dir is None
        and (
            args.model != OFFICIAL_QWEN_MODEL
            or args.revision != OFFICIAL_QWEN_REVISION
        )
    ):
        raise SystemExit(
            "the canonical QWEN_BASELINE_V1 path requires the official pinned model; "
            "use --output-dir for another model or revision"
        )
    try:
        output_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise SystemExit(
            f"refusing to overwrite existing first-attempt output: {output_dir}"
        ) from exc

    gpu = _gpu_metadata(args.gpu_model, args.gpu_count)
    manifest = {
        "artifact_name": SMOKE_NAME if args.mode == "smoke" else BASELINE_NAME,
        "mode": args.mode,
        "status": "RUNNING",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": {
            "id": args.model,
            "revision": args.revision,
            "manifest_path": None if manifest_path is None else str(manifest_path),
            "manifest": model_manifest,
        },
        "backend": {
            "type": "OpenAI-compatible",
            "server": "vLLM",
            "version_response": version,
            "served_model_ids": served_ids,
        },
        "interpreter": {
            "prompt_version": PROMPT_VERSION,
            "prompt_sha256": prompt_contract_hash(),
            "candidate_schema_version": SCHEMA_VERSION,
            "canonical_schema_hash": schema_plan.canonical_schema_hash,
            "canonical_validator": "jsonschema.Draft202012Validator",
            "gold_or_formal_answers_in_prompt": False,
            "llm_authorizes_recovery": False,
        },
        "structured_output": schema_plan.report_dict(),
        "decoding": config.public_dict(),
        "hardware": {
            **gpu,
            "quantization": args.quantization,
            "dtype": args.dtype,
            "served_max_model_len": args.served_max_model_len,
            "tensor_parallel_size": args.tensor_parallel_size,
        },
        "dataset": {"seed": dataset.seed, "case_count": len(selected)},
    }
    _write_json_exclusive(output_dir / "manifest.json", manifest)
    cases_dir = output_dir / "cases"
    cases_dir.mkdir()

    def preserve_case(outcome: LLMCaseOutcome) -> None:
        _write_json_exclusive(
            cases_dir / f"{outcome.case.scenario_id}.json", outcome.as_dict()
        )

    evaluation = evaluate_llm_incident_interpreter(
        LLMIncidentInterpreter(backend),
        dataset,
        cases=selected,
        case_callback=preserve_case,
    )
    _write_json_exclusive(output_dir / "evaluation.json", evaluation.as_dict())
    smoke_checks = _smoke_checks(evaluation.outcomes[0]) if args.mode == "smoke" else None
    completed = {
        "status": (
            "PASS"
            if smoke_checks is not None and all(smoke_checks.values())
            else "FAIL"
            if smoke_checks is not None
            else "COMPLETE"
        ),
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "completed_case_count": len(evaluation.outcomes),
        "case_failure_count": evaluation.metrics["case_failures"],
        "smoke_checks": smoke_checks,
        "failure_layer": (
            _smoke_failure_layer(evaluation.outcomes[0], smoke_checks)
            if smoke_checks is not None
            else None
        ),
        "metrics": evaluation.metrics,
    }
    _write_json_exclusive(output_dir / "completion.json", completed)
    print(json.dumps({"output_dir": str(output_dir), **completed}, indent=2))
    return 0 if smoke_checks is None or all(smoke_checks.values()) else 2


def _smoke_checks(outcome: LLMCaseOutcome) -> dict[str, bool]:
    pipeline = outcome.pipeline
    canonical_status, provenance_status = _validation_statuses(outcome)
    provenance_valid = (
        provenance_status == "PASS"
        and outcome.provenance.total_references
        == outcome.provenance.valid_references
    )
    return {
        "server_reachable": outcome.backend_response is not None,
        "model_returned_response": outcome.backend_response is not None,
        "response_parsed": canonical_status in {"PASS", "FAIL"},
        "candidate_schema_valid": canonical_status == "PASS",
        "canonical_schema_valid": canonical_status == "PASS",
        "provenance_valid": provenance_valid,
        "all_cited_evidence_ids_exist": (
            outcome.candidate is not None
            and outcome.provenance.total_references
            == outcome.provenance.valid_references
            and not outcome.provenance.fabricated_ids
        ),
        "grounding_executed": pipeline is not None,
        "formal_assessment_executed": (
            pipeline is not None and pipeline.formal_assessment is not None
        ),
        "online_cleo_not_invoked": (
            pipeline is None or not pipeline.online_prover_invoked
        ),
        "llm_did_not_directly_authorize_recovery": True,
    }


def _smoke_failure_layer(
    outcome: LLMCaseOutcome, checks: Mapping[str, bool]
) -> str | None:
    if all(checks.values()):
        return None
    message = outcome.error_message or ""
    if outcome.error_type == "StructuredOutputCompatibilityError" or (
        outcome.error_type == "BackendError"
        and any(
            marker in message.lower()
            for marker in ("json schema", "structured-output", "xgrammar", "guidance")
        )
    ):
        return "GENERATION_SCHEMA_FAILURE"
    if outcome.error_type == "BackendError":
        return "MODEL_SERVER_FAILURE"
    if outcome.error_type == "CandidateValidationError":
        if "not JSON" in message:
            return "MODEL_OUTPUT_INVALID_JSON"
        if "canonical CandidateRecoveryContext schema" in message:
            return "CANONICAL_SCHEMA_FAILURE"
        return "PROVENANCE_FAILURE"
    if outcome.pipeline is None:
        return "DOWNSTREAM_PIPELINE_FAILURE"
    if not outcome.pipeline.grounding.succeeded:
        return "GROUNDING_REJECTION"
    if outcome.pipeline.formal_assessment is None:
        return "DOWNSTREAM_PIPELINE_FAILURE"
    return "DOWNSTREAM_PIPELINE_FAILURE"


def _served_model_ids(response: Mapping[str, object]) -> list[str]:
    data = response.get("data")
    if not isinstance(data, list):
        raise SystemExit("LLM /models response does not contain a data array")
    return sorted(
        item["id"]
        for item in data
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    )


def _load_model_manifest(path: Path | None) -> Mapping[str, object] | None:
    if path is None:
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot read model manifest {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise SystemExit(f"model manifest must be a JSON object: {path}")
    return document


def _resolve_model_manifest_path(
    configured: Path | None, model: str, revision: str
) -> Path | None:
    if configured is not None:
        return configured
    if model != OFFICIAL_QWEN_MODEL:
        return None
    repository_root = Path(__file__).resolve().parent.parent
    model_root = Path(
        os.environ.get("DRICS_MODEL_DIR", str(repository_root.parent / "drics-llm" / "models"))
    )
    candidate = (
        model_root
        / "Qwen--Qwen3.5-9B"
        / revision
        / "DRICS_MODEL_MANIFEST.json"
    )
    return candidate if candidate.is_file() else None


def _validate_official_model_manifest(
    manifest: Mapping[str, object], revision: str
) -> None:
    expected = {
        "model_id": OFFICIAL_QWEN_MODEL,
        "requested_revision": revision,
        "resolved_commit": revision,
        "parameter_count": 9_653_104_368,
        "tensor_bytes": 19_306_310_880,
        "public": True,
        "gated": False,
        "license": "apache-2.0",
    }
    mismatches = {
        key: {"expected": value, "actual": manifest.get(key)}
        for key, value in expected.items()
        if manifest.get(key) != value
    }
    if mismatches:
        raise SystemExit(f"official model manifest mismatch: {mismatches}")


def _validate_vllm_version(version: Mapping[str, object] | None) -> None:
    if version is None or not isinstance(version.get("version"), str):
        raise SystemExit(
            "the official Qwen baseline requires a vLLM /version response"
        )
    raw = version["version"]
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", raw)
    if match is None:
        raise SystemExit(f"cannot parse vLLM server version: {raw!r}")
    parsed = tuple(int(item) for item in match.groups())
    if parsed < (0, 17, 0):
        raise SystemExit(
            f"vLLM {raw} is too old for the official Qwen3.5 recipe; require >=0.17.0"
        )


def _gpu_metadata(
    configured_model: str | None, configured_count: int | None
) -> dict[str, object]:
    if configured_model is not None:
        return {
            "gpu_model": configured_model,
            "gpu_count": configured_count,
            "source": "operator_environment",
        }
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        rows = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.SubprocessError):
        rows = []
    return {
        "gpu_model": None if not rows else rows[0].split(",", 1)[0].strip(),
        "gpu_count": configured_count if configured_count is not None else len(rows),
        "nvidia_smi_rows": rows,
        "source": "client_nvidia_smi" if rows else "unavailable",
    }


def _write_json_exclusive(path: Path, document: Mapping[str, object]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(document, stream, indent=2, sort_keys=True)
        stream.write("\n")


def _optional_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    return int(value)


def _optional_path(value: str | None) -> Path | None:
    return None if value is None or not value.strip() else Path(value)


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    return default if value is None or not value.strip() else float(value)


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return default if value is None or not value.strip() else int(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


if __name__ == "__main__":
    raise SystemExit(main())
