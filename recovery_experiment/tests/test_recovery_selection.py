from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from recovery_experiment.certificate import CertificateCoverageResult, CertificateStatus
from recovery_experiment.recovery_selection import (
    CONTROLLED_HOLD,
    FLOWING_TAKEOVER,
    CertificatePaths,
    SelectionStatus,
    select_recovery_policy,
)
from recovery_experiment.recovery_selection_evaluation import (
    evaluate_selection_scenarios,
    selection_scenarios,
)


def _candidates(selection):
    return {candidate.policy: candidate for candidate in selection.candidates}


class RecoverySelectionTests(unittest.TestCase):
    def test_continuous_service_selects_flowing_policy_not_safe_hold(self) -> None:
        selection = select_recovery_policy(selection_scenarios()["flowing_service_qualified"].incident)
        candidates = _candidates(selection)
        self.assertEqual(selection.selected_policy, FLOWING_TAKEOVER)
        self.assertEqual(candidates[CONTROLLED_HOLD].certificate.status, CertificateStatus.COVERED_BY_CERTIFICATE)
        self.assertEqual(
            candidates[CONTROLLED_HOLD].status,
            SelectionStatus.COVERED_SERVICE_INADEQUATE,
        )
        self.assertEqual(candidates[FLOWING_TAKEOVER].status, SelectionStatus.ADMISSIBLE)

    def test_state_margin_rejects_flowing_without_rejecting_controlled_hold(self) -> None:
        selection = select_recovery_policy(selection_scenarios()["state_margin_fallback_to_hold"].incident)
        candidates = _candidates(selection)
        self.assertEqual(selection.selected_policy, CONTROLLED_HOLD)
        self.assertEqual(candidates[CONTROLLED_HOLD].status, SelectionStatus.ADMISSIBLE)
        self.assertEqual(candidates[FLOWING_TAKEOVER].status, SelectionStatus.NOT_COVERED)
        self.assertTrue(candidates[CONTROLLED_HOLD].trace["safe"])
        self.assertFalse(candidates[FLOWING_TAKEOVER].trace["safe"])

    def test_costs_use_one_external_demand_horizon_and_weight_set(self) -> None:
        scenario = selection_scenarios()["both_covered_cost_comparison"]
        selection = select_recovery_policy(scenario.incident)
        candidates = _candidates(selection)
        hold, flowing = candidates[CONTROLLED_HOLD], candidates[FLOWING_TAKEOVER]
        self.assertEqual(selection.selected_policy, FLOWING_TAKEOVER)
        self.assertEqual(hold.trace["external_demand"], 1.5)
        self.assertEqual(flowing.trace["external_demand"], 1.5)
        self.assertEqual(hold.trace["evaluation_horizon"], flowing.trace["evaluation_horizon"])
        self.assertEqual(hold.trace["candidate_theorem_horizon"], 6.0)
        self.assertEqual(flowing.trace["candidate_theorem_horizon"], 6.0)
        self.assertEqual(hold.cost.service_loss, 9.0)
        self.assertAlmostEqual(flowing.cost.service_loss, 0.3)
        self.assertLess(flowing.cost.total, hold.cost.total)
        self.assertEqual(hold.as_dict()["cost_interpretation"]["formal_cost_bound"], None)
        self.assertEqual(hold.as_dict()["cost_interpretation"]["estimated_before_selection"], hold.cost.as_dict())
        self.assertEqual(
            hold.as_dict()["cost_interpretation"]["observed_from_completed_simulation"], hold.cost.as_dict()
        )
        self.assertTrue(hold.cost_comparable)
        self.assertTrue(flowing.cost_comparable)

    def test_common_horizon_distinguishes_safe_hold_from_takeover_timeline(self) -> None:
        selection = select_recovery_policy(selection_scenarios()["both_covered_cost_comparison"].incident)
        candidates = _candidates(selection)
        hold_horizon = candidates[CONTROLLED_HOLD].guarantee.formal_horizon
        flowing_horizon = candidates[FLOWING_TAKEOVER].guarantee.formal_horizon
        self.assertEqual(hold_horizon.startup_duration, 0.0)
        self.assertEqual(hold_horizon.post_takeover_operation_duration, 6.0)
        self.assertEqual(flowing_horizon.startup_duration, 1.0)
        self.assertEqual(flowing_horizon.post_takeover_operation_duration, 5.0)
        self.assertEqual(hold_horizon.total_duration, flowing_horizon.total_duration)

    def test_controlled_safe_hold_requires_full_horizon_interruption_allowance(self) -> None:
        selection = select_recovery_policy(selection_scenarios()["both_covered_cost_comparison"].incident)
        hold = _candidates(selection)[CONTROLLED_HOLD]
        self.assertEqual(hold.guarantee.startup_interruption_duration, 6.0)
        self.assertEqual(hold.guarantee.startup_delivery_lower_bound, 0.0)
        self.assertTrue(all(value == 0.0 for value in hold.trace["startup_delivery"]))

    def test_hold_is_not_authorized_when_only_part_of_its_interruption_is_permitted(self) -> None:
        scenario = selection_scenarios()["both_covered_cost_comparison"]
        limited_interruption = replace(
            scenario.incident.service,
            permitted_interruption_duration=0.5,
        )
        selection = select_recovery_policy(replace(scenario.incident, service=limited_interruption))
        candidates = _candidates(selection)
        self.assertEqual(candidates[CONTROLLED_HOLD].status, SelectionStatus.COVERED_SERVICE_INADEQUATE)
        self.assertIn("startup interruption is longer", candidates[CONTROLLED_HOLD].reasons[0])
        self.assertEqual(candidates[FLOWING_TAKEOVER].status, SelectionStatus.ADMISSIBLE)

    def test_contract_cannot_authorize_duration_beyond_common_horizon(self) -> None:
        scenario = selection_scenarios()["both_covered_cost_comparison"]
        too_long = replace(
            scenario.incident.service,
            assured_operation_duration=5.5,
        )
        selection = select_recovery_policy(replace(scenario.incident, service=too_long))
        self.assertIsNone(selection.selected_policy)
        self.assertTrue(
            all(candidate.status is SelectionStatus.INVALID_OR_INCOMPATIBLE for candidate in selection.candidates)
        )

    def test_full_continuous_external_demand_leaves_no_authorized_candidate(self) -> None:
        selection = select_recovery_policy(selection_scenarios()["neither_meets_full_external_delivery"].incident)
        candidates = _candidates(selection)
        self.assertIsNone(selection.selected_policy)
        self.assertEqual(candidates[CONTROLLED_HOLD].status, SelectionStatus.COVERED_SERVICE_INADEQUATE)
        self.assertEqual(candidates[FLOWING_TAKEOVER].status, SelectionStatus.COVERED_SERVICE_INADEQUATE)
        self.assertEqual(candidates[FLOWING_TAKEOVER].guarantee.startup_delivery_lower_bound, 1.2)
        self.assertLess(
            candidates[FLOWING_TAKEOVER].guarantee.startup_delivery_lower_bound,
            selection.incident.service.external_demand,
        )

    def test_missing_trusted_isolation_and_incompatible_topology_are_not_authorized(self) -> None:
        for name in ("missing_trusted_isolation", "incompatible_topology"):
            selection = select_recovery_policy(selection_scenarios()[name].incident)
            self.assertIsNone(selection.selected_policy, name)
            self.assertTrue(
                all(
                    candidate.status is SelectionStatus.INVALID_OR_INCOMPATIBLE
                    for candidate in selection.candidates
                ),
                name,
            )

    def test_untrusted_or_other_policy_manifest_cannot_authorize_a_candidate(self) -> None:
        scenario = selection_scenarios()["both_covered_cost_comparison"]
        selection = select_recovery_policy(
            scenario.incident,
            certificate_paths=CertificatePaths(controlled_hold=Path("unreviewed-controlled-manifest.json")),
        )
        candidates = _candidates(selection)
        self.assertEqual(candidates[CONTROLLED_HOLD].status, SelectionStatus.UNTRUSTED)
        self.assertEqual(candidates[FLOWING_TAKEOVER].status, SelectionStatus.ADMISSIBLE)
        self.assertEqual(selection.selected_policy, FLOWING_TAKEOVER)

    def test_selection_never_invokes_cleo(self) -> None:
        scenario = selection_scenarios()["both_covered_cost_comparison"]
        with patch(
            "recovery_experiment.verify_parameterized_recovery.verify_parameterized_theorem",
            side_effect=AssertionError("selection must not invoke CLEO"),
        ), patch(
            "recovery_experiment.verify_state_dependent_recovery.verify_state_dependent_theorem",
            side_effect=AssertionError("selection must not invoke CLEO"),
        ):
            selection = select_recovery_policy(scenario.incident)
        self.assertEqual(selection.selected_policy, FLOWING_TAKEOVER)

    def test_unverified_formal_result_is_not_authorizing(self) -> None:
        scenario = selection_scenarios()["both_covered_cost_comparison"]
        unavailable = CertificateCoverageResult(
            CertificateStatus.UNVERIFIED,
            ("reviewed theorem is unresolved",),
            0.0,
            "two-tank-flowing-takeover-state-dependent-v1",
        )
        with patch(
            "recovery_experiment.recovery_selection.check_state_dependent_recovery",
            return_value=unavailable,
        ):
            selection = select_recovery_policy(scenario.incident)
        candidates = _candidates(selection)
        self.assertEqual(
            candidates[FLOWING_TAKEOVER].status,
            SelectionStatus.FORMAL_GUARANTEE_UNAVAILABLE,
        )
        self.assertEqual(selection.selected_policy, CONTROLLED_HOLD)

    def test_cost_based_selection_requires_trace_estimation(self) -> None:
        scenario = selection_scenarios()["both_covered_cost_comparison"]
        selection = select_recovery_policy(scenario.incident, simulate_for_diagnostics=False)
        self.assertIsNone(selection.selected_policy)
        self.assertIn("cost estimation was not run", selection.selection_reason)
        self.assertTrue(all(candidate.cost is None for candidate in selection.candidates))
        self.assertTrue(all(not candidate.cost_comparable for candidate in selection.candidates))

    def test_evaluation_is_reproducible_except_for_measured_latency(self) -> None:
        one = evaluate_selection_scenarios()
        two = evaluate_selection_scenarios()
        for name, first in one["scenarios"].items():
            second = two["scenarios"][name]
            left, right = first["selection"], second["selection"]
            self.assertEqual(left["incident"], right["incident"], name)
            self.assertEqual(left["selected_policy"], right["selected_policy"], name)
            self.assertEqual(left["selection_reason"], right["selection_reason"], name)
            for first_candidate, second_candidate in zip(left["candidates"], right["candidates"]):
                self.assertEqual(first_candidate["policy"], second_candidate["policy"])
                self.assertEqual(first_candidate["status"], second_candidate["status"])
                self.assertEqual(first_candidate["certificate"]["status"], second_candidate["certificate"]["status"])
                self.assertEqual(first_candidate["reasons"], second_candidate["reasons"])
                self.assertEqual(first_candidate["trace"], second_candidate["trace"])
                self.assertEqual(first_candidate["cost"], second_candidate["cost"])
