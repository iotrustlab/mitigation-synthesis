"""Regression tests for the evidence-to-grounded-context front end."""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from recovery_experiment.candidate_context import CandidateClaim, CandidateStatus
from recovery_experiment.context_grounding import GroundingStatus, ground_candidate_context
from recovery_experiment.incident_dataset import (
    DATASET_SEED,
    FLOWING_TEMPLATE,
    SAFE_HOLD_TEMPLATE,
    build_synthetic_incident_dataset,
)
from recovery_experiment.incident_evidence import IncidentEvidence
from recovery_experiment.incident_evidence_evaluation import (
    ErrorPropagationCategory,
    evaluate_deterministic_pipeline,
)
from recovery_experiment.incident_interpreter import DeterministicIncidentInterpreter
from recovery_experiment.incident_pipeline import IncidentPipelineStatus, run_incident_pipeline


class IncidentEvidencePipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = build_synthetic_incident_dataset()
        cls.by_id = {case.scenario_id: case for case in cls.dataset.cases}

    def _candidate(self, scenario_id: str):
        return DeterministicIncidentInterpreter().interpret(self.by_id[scenario_id].evidence)

    def _ground(self, scenario_id: str):
        case = self.by_id[scenario_id]
        return ground_candidate_context(
            self._candidate(scenario_id), case.trusted_plant_knowledge, case.recovery_configuration
        )

    def test_deterministic_json_round_trip(self) -> None:
        evidence = self.by_id["A-immediate-nominal-1"].evidence
        self.assertEqual(IncidentEvidence.from_json(evidence.to_json()), evidence)
        self.assertEqual(IncidentEvidence.from_json(evidence.to_json()).to_json(), evidence.to_json())

    def test_candidate_and_grounded_provenance_are_retained(self) -> None:
        candidate = self._candidate("A-immediate-nominal-1")
        self.assertEqual(candidate.x1.status, CandidateStatus.OBSERVED)
        self.assertEqual(candidate.suspected_compromised_component.status, CandidateStatus.DERIVED)
        self.assertTrue(candidate.x1.evidence_ids)
        result = self._ground("A-immediate-nominal-1")
        self.assertTrue(result.succeeded)
        assert result.grounded is not None
        self.assertIn("observation:x1", result.grounded.provenance_for("x1").evidence_ids[0])
        self.assertTrue(result.grounded.provenance_for("x1").knowledge_ids)

    def test_missing_conflicting_and_no_default_timing_are_structured(self) -> None:
        self.assertEqual(self._ground("J-conflicting-p2").status, GroundingStatus.CONFLICTING_EVIDENCE)
        self.assertEqual(self._ground("K-missing-x2").status, GroundingStatus.INSUFFICIENT_EVIDENCE)
        self.assertEqual(self._ground("K-missing-p2-health").status, GroundingStatus.UNKNOWN_RESOURCE_STATUS)
        # The case removes timing evidence and the recovery configuration value.
        self.assertEqual(
            self._ground("K-missing-isolation-timing").status,
            GroundingStatus.MISSING_TIMING_INFORMATION,
        )

    def test_unknown_component_and_unsupported_capability_are_rejected(self) -> None:
        case = self.by_id["A-immediate-nominal-1"]
        candidate = self._candidate(case.scenario_id)
        unknown_component = replace(
            candidate,
            suspected_compromised_component=CandidateClaim(
                "P9", CandidateStatus.DERIVED, evidence_ids=("test:component",), sources=("synthetic_ids",)
            ),
        )
        self.assertEqual(
            ground_candidate_context(unknown_component, case.trusted_plant_knowledge, case.recovery_configuration).status,
            GroundingStatus.UNSUPPORTED_COMPONENT,
        )
        unsupported_capability = replace(
            candidate,
            attacker_capability=CandidateClaim(
                "write_downstream_plc", CandidateStatus.DERIVED, evidence_ids=("test:capability",), sources=("synthetic_ids",)
            ),
        )
        self.assertEqual(
            ground_candidate_context(unsupported_capability, case.trusted_plant_knowledge, case.recovery_configuration).status,
            GroundingStatus.UNSUPPORTED_ATTACK_CAPABILITY,
        )

    def test_p2_untrusted_or_unavailable_never_becomes_takeover_authority(self) -> None:
        for scenario_id in ("C-p2-unavailable-1", "D-p2-untrusted-1"):
            result = self._ground(scenario_id)
            self.assertTrue(result.succeeded)
            assert result.grounded is not None
            self.assertFalse(result.grounded.context.resource_availability.trusted_backup_available)
            pipeline = run_incident_pipeline(
                self.by_id[scenario_id].evidence,
                self.by_id[scenario_id].trusted_plant_knowledge,
                self.by_id[scenario_id].recovery_configuration,
            )
            assert pipeline.formal_assessment is not None
            self.assertEqual(
                tuple(item.value for item in pipeline.formal_assessment.applicability.applicable_templates),
                (SAFE_HOLD_TEMPLATE,),
            )

    def test_isolation_and_hold_control_constraints_gate_templates(self) -> None:
        no_isolation = run_incident_pipeline(
            self.by_id["F-isolation-unavailable-1"].evidence,
            self.by_id["F-isolation-unavailable-1"].trusted_plant_knowledge,
            self.by_id["F-isolation-unavailable-1"].recovery_configuration,
        )
        assert no_isolation.formal_assessment is not None
        self.assertEqual(no_isolation.formal_assessment.applicability.applicable_templates, ())

        hold_unavailable = run_incident_pipeline(
            self.by_id["E-hold-controls-unavailable-1"].evidence,
            self.by_id["E-hold-controls-unavailable-1"].trusted_plant_knowledge,
            self.by_id["E-hold-controls-unavailable-1"].recovery_configuration,
        )
        assert hold_unavailable.formal_assessment is not None
        self.assertEqual(
            tuple(item.value for item in hold_unavailable.formal_assessment.applicability.applicable_templates),
            (FLOWING_TEMPLATE,),
        )

    def test_state_and_unsupported_timing_are_preserved_without_rounding(self) -> None:
        candidate = self._candidate("G-margin-outside-1")
        self.assertEqual((candidate.x1.value, candidate.x2.value), (4.0, 3.0))
        timing = run_incident_pipeline(
            self.by_id["I-unsupported-timing-1"].evidence,
            self.by_id["I-unsupported-timing-1"].trusted_plant_knowledge,
            self.by_id["I-unsupported-timing-1"].recovery_configuration,
        )
        assert timing.grounding.grounded is not None
        self.assertEqual(timing.grounding.grounded.context.plant.isolation_delay, 0.75)
        assert timing.formal_assessment is not None
        flowing = next(
            item for item in timing.formal_assessment.templates if item.template_id.value == FLOWING_TEMPLATE
        )
        assert flowing.construction is not None
        self.assertIsNone(flowing.construction.formal_model_id)

    def test_grounding_failure_prevents_formal_construction(self) -> None:
        case = self.by_id["K-missing-x2"]
        with patch("recovery_experiment.incident_pipeline.assess_template_formal_problems") as formal:
            result = run_incident_pipeline(case.evidence, case.trusted_plant_knowledge, case.recovery_configuration)
        self.assertEqual(result.status, IncidentPipelineStatus.GROUNDING_FAILED)
        self.assertIsNone(result.formal_assessment)
        self.assertIsNone(result.selection)
        self.assertFalse(result.online_prover_invoked)
        formal.assert_not_called()

    def test_template_certificate_and_selection_are_not_cross_reused(self) -> None:
        baseline = run_incident_pipeline(
            self.by_id["A-immediate-nominal-1"].evidence,
            self.by_id["A-immediate-nominal-1"].trusted_plant_knowledge,
            self.by_id["A-immediate-nominal-1"].recovery_configuration,
        )
        assert baseline.formal_assessment is not None and baseline.selection is not None
        artifacts = {item.template_id.value: item for item in baseline.formal_assessment.templates}
        self.assertNotEqual(
            artifacts[FLOWING_TEMPLATE].certificate.certificate_id,
            artifacts[SAFE_HOLD_TEMPLATE].certificate.certificate_id,
        )
        self.assertEqual(baseline.selection.selected_policy, FLOWING_TEMPLATE)

        boundary = run_incident_pipeline(
            self.by_id["G-margin-outside-1"].evidence,
            self.by_id["G-margin-outside-1"].trusted_plant_knowledge,
            self.by_id["G-margin-outside-1"].recovery_configuration,
        )
        assert boundary.formal_assessment is not None and boundary.selection is not None
        flowing = next(item for item in boundary.formal_assessment.templates if item.template_id.value == FLOWING_TEMPLATE)
        holding = next(item for item in boundary.formal_assessment.templates if item.template_id.value == SAFE_HOLD_TEMPLATE)
        self.assertFalse(flowing.certificate.covered)
        self.assertTrue(holding.certificate.covered)
        self.assertEqual(boundary.selection.selected_policy, SAFE_HOLD_TEMPLATE)

    def test_dataset_is_fixed_seed_and_independent_from_interpreter_implementation(self) -> None:
        again = build_synthetic_incident_dataset(DATASET_SEED)
        self.assertEqual(self.dataset, again)
        self.assertGreaterEqual(len(self.dataset.cases), 20)
        self.assertLessEqual(len(self.dataset.cases), 50)
        source = Path(__file__).resolve().parents[1] / "incident_dataset.py"
        tree = ast.parse(source.read_text())
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        self.assertNotIn("incident_interpreter", imported_modules)

    def test_full_deterministic_pipeline_is_reproducible_against_gold(self) -> None:
        report = evaluate_deterministic_pipeline(self.dataset)
        self.assertEqual(report.case_count, 27)
        self.assertEqual(report.grounding.false_acceptance, 0)
        self.assertEqual(report.grounding.false_rejection, 0)
        self.assertEqual(report.recovery_decision_accuracy.value, 1.0)
        self.assertEqual(
            dict(report.first_divergence_counts)[ErrorPropagationCategory.NO_DIVERGENCE.value],
            report.case_count,
        )


if __name__ == "__main__":
    unittest.main()
