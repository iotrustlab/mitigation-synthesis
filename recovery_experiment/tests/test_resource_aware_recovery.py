from __future__ import annotations

import os
import unittest
from dataclasses import replace

from recovery_experiment.certificate import CertificateStatus
from recovery_experiment.context import ContextValidationError
from recovery_experiment.controlled_safe_hold_certificate import check_controlled_safe_hold_recovery
from recovery_experiment.controlled_safe_hold_formal import (
    CONTROLLED_SAFE_HOLD_MODEL_ID,
    CONTROLLED_SAFE_HOLD_PLANT_MODEL_ID,
    CONTROLLED_SAFE_HOLD_POLICY_ID,
    CONTROLLED_SAFE_HOLD_PROOF_PROFILE_ID,
)
from recovery_experiment.experiment import run_scenario
from recovery_experiment.formal import FormalStatus
from recovery_experiment.formal_problem import assess_template_formal_problems, construct_template_formal_problems
from recovery_experiment.model import AttackerAction
from recovery_experiment.policies import PersistentPrimaryAttacker, TrustedControlledSafeHoldPolicy
from recovery_experiment.recovery_selection import (
    CONTROLLED_SAFE_HOLD,
    FLOWING_TAKEOVER,
    RecoverySelectionStatus,
    SelectionStatus,
    incident_from_context,
    select_recovery_policy,
)
from recovery_experiment.recovery_templates import (
    RecoveryTemplateId,
    TemplateApplicabilityStatus,
    assess_recovery_template_applicability,
)
from recovery_experiment.resource_aware_evaluation import resource_aware_scenarios
from recovery_experiment.scenarios import context_for
from recovery_experiment.state_dependent_certificate import check_state_dependent_recovery
from recovery_experiment.state_dependent_formal import (
    STATE_DEPENDENT_PLANT_MODEL_ID,
    STATE_DEPENDENT_POLICY_ID,
)


def _candidates(selection):
    return {candidate.policy: candidate for candidate in selection.candidates}


class ResourceAwareRecoveryTests(unittest.TestCase):
    def test_resource_availability_is_explicit_and_has_no_silent_default(self) -> None:
        baseline = resource_aware_scenarios()["A_backup_available"].context
        with self.assertRaises(ContextValidationError):
            replace(baseline, resource_availability=None).validate()
        with self.assertRaises(ContextValidationError):
            replace(baseline, control_path_authority=None).validate()
        with self.assertRaises(ContextValidationError):
            replace(
                baseline,
                control_path_authority=replace(
                    baseline.control_path_authority,
                    operational=baseline.control_path_authority.operational - {"P2_command"},
                ),
            ).validate()
        self.assertTrue(baseline.resource_availability.trusted_backup_available)

    def test_backup_unavailable_excludes_takeover_and_constructs_safe_hold(self) -> None:
        scenario = resource_aware_scenarios()["B_backup_unavailable_hold"]
        report = assess_recovery_template_applicability(scenario.context)
        self.assertEqual(
            report.for_template(RecoveryTemplateId.FLOWING_BACKUP_TAKEOVER).status,
            TemplateApplicabilityStatus.NOT_APPLICABLE,
        )
        self.assertTrue(report.for_template(RecoveryTemplateId.CONTROLLED_SAFE_HOLD).applicable)
        formal = construct_template_formal_problems(scenario.context)
        self.assertIsNone(formal[0].construction)
        self.assertEqual(formal[1].construction.formal_model_id, CONTROLLED_SAFE_HOLD_MODEL_ID)
        selection = select_recovery_policy(scenario.incident)
        self.assertEqual([candidate.policy for candidate in selection.candidates], [CONTROLLED_SAFE_HOLD])
        self.assertEqual(selection.selected_policy, CONTROLLED_SAFE_HOLD)
        flowing_projection = replace(
            scenario.context,
            plant_model_id=STATE_DEPENDENT_PLANT_MODEL_ID,
            recovery_policy_id=STATE_DEPENDENT_POLICY_ID,
        )
        self.assertEqual(
            check_state_dependent_recovery(flowing_projection).status,
            CertificateStatus.NOT_COVERED_BY_CERTIFICATE,
        )

    def test_missing_hold_controls_excludes_safe_hold(self) -> None:
        scenario = resource_aware_scenarios()["F_missing_trusted_hold_gate"]
        report = assess_recovery_template_applicability(scenario.context)
        hold = report.for_template(RecoveryTemplateId.CONTROLLED_SAFE_HOLD)
        self.assertEqual(hold.status, TemplateApplicabilityStatus.NOT_APPLICABLE)
        self.assertIn("trusted_demand_control_available", hold.reasons[0])
        self.assertIsNone(construct_template_formal_problems(scenario.context)[1].construction)

    def test_no_isolation_reports_no_supported_template_without_global_claim(self) -> None:
        scenario = resource_aware_scenarios()["E_no_trusted_isolation"]
        selection = select_recovery_policy(scenario.incident)
        self.assertEqual(selection.status, RecoverySelectionStatus.NO_SUPPORTED_TEMPLATE)
        self.assertEqual(selection.candidates, ())
        self.assertIn("does not claim global recovery infeasibility", selection.selection_reason)

    def test_safe_hold_has_its_own_model_profile_and_certificate(self) -> None:
        formal = assess_template_formal_problems(resource_aware_scenarios()["B_backup_unavailable_hold"].context)
        hold = next(item for item in formal.templates if item.template_id is RecoveryTemplateId.CONTROLLED_SAFE_HOLD)
        self.assertEqual(hold.construction.formal_model_id, CONTROLLED_SAFE_HOLD_MODEL_ID)
        self.assertEqual(hold.construction.proof_profile, CONTROLLED_SAFE_HOLD_PROOF_PROFILE_ID)
        self.assertTrue(hold.certificate.covered)

    def test_certificates_do_not_cross_authorize(self) -> None:
        baseline = resource_aware_scenarios()["A_backup_available"].context
        hold_context = replace(
            baseline,
            plant_model_id=CONTROLLED_SAFE_HOLD_PLANT_MODEL_ID,
            recovery_policy_id=CONTROLLED_SAFE_HOLD_POLICY_ID,
        )
        flowing_context = replace(
            baseline,
            plant_model_id=STATE_DEPENDENT_PLANT_MODEL_ID,
            recovery_policy_id=STATE_DEPENDENT_POLICY_ID,
        )
        self.assertTrue(check_controlled_safe_hold_recovery(hold_context).covered)
        self.assertEqual(
            check_state_dependent_recovery(hold_context).status,
            CertificateStatus.INCOMPATIBLE_CONTEXT,
        )
        self.assertEqual(
            check_controlled_safe_hold_recovery(flowing_context).status,
            CertificateStatus.INCOMPATIBLE_CONTEXT,
        )

    def test_positive_uninterrupted_service_excludes_safety_covered_hold(self) -> None:
        scenario = resource_aware_scenarios()["C_positive_continuous_service_without_backup"]
        formal = assess_template_formal_problems(scenario.context)
        hold = next(item for item in formal.templates if item.template_id is RecoveryTemplateId.CONTROLLED_SAFE_HOLD)
        self.assertTrue(hold.certificate.covered)
        selection = select_recovery_policy(scenario.incident)
        candidate = _candidates(selection)[CONTROLLED_SAFE_HOLD]
        self.assertEqual(candidate.status, SelectionStatus.COVERED_SERVICE_INADEQUATE)
        self.assertIsNone(candidate.cost)
        self.assertIsNone(selection.selected_policy)

    def test_cost_comparison_only_uses_formally_admissible_candidates(self) -> None:
        scenario = resource_aware_scenarios()["D_both_resources_interruption_allowed"]
        selection = select_recovery_policy(scenario.incident)
        candidates = _candidates(selection)
        self.assertEqual(set(candidates), {CONTROLLED_SAFE_HOLD, FLOWING_TAKEOVER})
        self.assertTrue(all(candidate.admissible for candidate in candidates.values()))
        self.assertTrue(all(candidate.cost is not None for candidate in candidates.values()))
        self.assertEqual(selection.selected_policy, FLOWING_TAKEOVER)
        self.assertEqual(candidates[CONTROLLED_SAFE_HOLD].cost.backup_usage, 0.0)
        self.assertGreater(candidates[CONTROLLED_SAFE_HOLD].cost.service_loss, 0.0)

    def test_takeover_margin_failure_selects_safe_hold(self) -> None:
        scenario = resource_aware_scenarios()["G_takeover_margin_outside_hold_applies"]
        selection = select_recovery_policy(scenario.incident)
        candidates = _candidates(selection)
        self.assertEqual(candidates[FLOWING_TAKEOVER].status, SelectionStatus.NOT_COVERED)
        self.assertEqual(candidates[CONTROLLED_SAFE_HOLD].status, SelectionStatus.ADMISSIBLE)
        self.assertEqual(selection.selected_policy, CONTROLLED_SAFE_HOLD)

    def test_simulator_safe_hold_uses_independent_isolation_and_no_backup(self) -> None:
        context = resource_aware_scenarios()["B_backup_unavailable_hold"].context
        result = run_scenario(
            "safe_hold_simulator_contract",
            context.plant,
            PersistentPrimaryAttacker(AttackerAction.FORCE_PRIMARY_ON),
            TrustedControlledSafeHoldPolicy(),
            initial_state=context.current_state,
        )
        self.assertTrue(result.safe)
        self.assertTrue(all(row.primary_path_isolated for row in result.records))
        self.assertTrue(all(not row.p2_command and not row.p2_effective_state for row in result.records))
        self.assertTrue(all(row.q_in == row.q_out == row.q_delivered == 0.0 for row in result.records))

    def test_safe_hold_requires_immediate_isolation(self) -> None:
        scenario = resource_aware_scenarios()["A_backup_available"]
        delayed = context_for(replace(scenario.context.plant, isolation_delay=0.5))
        report = assess_recovery_template_applicability(delayed)
        hold = report.for_template(RecoveryTemplateId.CONTROLLED_SAFE_HOLD)
        self.assertEqual(hold.status, TemplateApplicabilityStatus.NOT_APPLICABLE)
        self.assertIn("immediate physical isolation only", hold.reasons[-1])

    @unittest.skipUnless(os.environ.get("RUN_CLEO_REGRESSION") == "1", "set RUN_CLEO_REGRESSION=1")
    def test_controlled_safe_hold_cleo_theorem_is_verified(self) -> None:
        from recovery_experiment.verify_controlled_safe_hold import verify_controlled_safe_hold_theorem

        self.assertEqual(verify_controlled_safe_hold_theorem().status, FormalStatus.VERIFIED)
