from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from recovery_experiment.certificate import CertificateStatus
from recovery_experiment.delayed_isolation_certificate import (
    TRUSTED_MANIFEST_SHA256,
    check_delayed_isolation_recovery,
)
from recovery_experiment.delayed_isolation_evaluation import (
    DELAYED_BINARY_SCHEDULES,
    delayed_isolation_scenarios,
    enumerate_delayed_schedule_costs,
)
from recovery_experiment.delayed_isolation_formal import (
    DELAYED_ISOLATION_PLANT_MODEL_ID,
    DELAYED_ISOLATION_POLICY_ID,
    render_delayed_isolation_recovery_envelope,
)
from recovery_experiment.model import AttackerAction
from recovery_experiment.recovery_selection import (
    DELAYED_FLOWING_TAKEOVER,
    incident_from_context,
    select_recovery_policy,
)
from recovery_experiment.state_dependent_certificate import check_state_dependent_recovery


class DelayedIsolationCertificateTests(unittest.TestCase):
    @staticmethod
    def _project(context):
        return replace(
            context,
            plant_model_id=DELAYED_ISOLATION_PLANT_MODEL_ID,
            recovery_policy_id=DELAYED_ISOLATION_POLICY_ID,
        )

    def test_static_artifact_matches_renderer_and_manifest_authorizes_exact_context(self) -> None:
        static = (Path(__file__).resolve().parents[1] / "delayed_isolation_recovery_takeover.envelope").read_text()
        self.assertEqual(static, render_delayed_isolation_recovery_envelope().envelope_text)
        scenario = delayed_isolation_scenarios()["delayed_safe_command_change"]
        self.assertEqual(
            check_delayed_isolation_recovery(
                self._project(scenario.context), attacker_schedule=scenario.attacker_schedule
            ).status,
            CertificateStatus.COVERED_BY_CERTIFICATE,
        )

    def test_every_theorem_permitted_schedule_uses_the_same_certificate(self) -> None:
        context = self._project(delayed_isolation_scenarios()["delayed_safe_command_change"].context)
        for schedule in DELAYED_BINARY_SCHEDULES:
            with self.subTest(schedule=schedule):
                self.assertEqual(
                    check_delayed_isolation_recovery(context, attacker_schedule=schedule).status,
                    CertificateStatus.COVERED_BY_CERTIFICATE,
                )

    def test_schedule_outside_the_two_pre_isolation_choices_is_not_covered(self) -> None:
        context = self._project(delayed_isolation_scenarios()["delayed_safe_command_change"].context)
        self.assertEqual(
            check_delayed_isolation_recovery(
                context,
                attacker_schedule=(
                    AttackerAction.FORCE_PRIMARY_OFF,
                    AttackerAction.FORCE_PRIMARY_ON,
                    AttackerAction.FORCE_PRIMARY_OFF,
                ),
            ).status,
            CertificateStatus.NOT_COVERED_BY_CERTIFICATE,
        )

    def test_immediate_certificate_cannot_authorize_delayed_context(self) -> None:
        delayed = self._project(delayed_isolation_scenarios()["delayed_safe_command_change"].context)
        self.assertEqual(
            check_state_dependent_recovery(delayed).status,
            CertificateStatus.INCOMPATIBLE_CONTEXT,
        )

    def test_delay_ratio_and_each_margin_failure_are_not_covered(self) -> None:
        scenarios = delayed_isolation_scenarios()
        for name in (
            "delayed_timing_outside_family",
            "delayed_t1_margin_insufficient",
            "delayed_t2_on_threat",
        ):
            with self.subTest(scenario=name):
                scenario = scenarios[name]
                self.assertEqual(
                    check_delayed_isolation_recovery(
                        self._project(scenario.context), attacker_schedule=scenario.attacker_schedule
                    ).status,
                    CertificateStatus.NOT_COVERED_BY_CERTIFICATE,
                )

    def test_alternate_manifest_or_changed_artifact_cannot_authorize(self) -> None:
        context = self._project(delayed_isolation_scenarios()["delayed_safe_command_change"].context)
        with tempfile.TemporaryDirectory() as directory:
            alternate = Path(directory) / "manifest.json"
            alternate.write_text('{"verification_status": "VERIFIED"}')
            self.assertEqual(
                check_delayed_isolation_recovery(context, manifest_path=alternate).status,
                CertificateStatus.UNTRUSTED_CERTIFICATE,
            )
        with patch(
            "recovery_experiment.delayed_isolation_certificate._sha256_bytes",
            side_effect=[TRUSTED_MANIFEST_SHA256, "changed-artifact-digest"],
        ):
            self.assertEqual(
                check_delayed_isolation_recovery(context).status,
                CertificateStatus.UNTRUSTED_CERTIFICATE,
            )

    def test_runtime_check_never_invokes_cleo(self) -> None:
        context = self._project(delayed_isolation_scenarios()["delayed_safe_command_change"].context)
        with patch(
            "recovery_experiment.verify_delayed_isolation_recovery.verify_delayed_isolation_theorem",
            side_effect=AssertionError("runtime checker must not invoke CLEO"),
        ):
            self.assertEqual(
                check_delayed_isolation_recovery(context).status,
                CertificateStatus.COVERED_BY_CERTIFICATE,
            )

    def test_schedule_enumeration_is_not_misreported_as_a_formal_cost_bound(self) -> None:
        report = enumerate_delayed_schedule_costs(
            delayed_isolation_scenarios()["delayed_safe_command_change"].context
        )
        self.assertEqual(len(report["observed_costs_by_schedule"]), 4)
        self.assertIn("not a formally proved hybrid-game cost bound", report["scope"])
        self.assertEqual(report["nominal_contract_minimum_cost"]["total"], 8.875)
        self.assertEqual(report["conservative_finite_schedule_cost"]["total"], 13.375)
        totals = {row["observed_simulated_cost"]["total"] for row in report["observed_costs_by_schedule"]}
        self.assertEqual(totals, {13.375})

    def test_delayed_selector_evaluates_only_the_matching_policy(self) -> None:
        scenario = delayed_isolation_scenarios()["delayed_safe_command_change"]
        selection = select_recovery_policy(
            incident_from_context(
                scenario.context,
                require_continuous_delivery=True,
                attacker_schedule=scenario.attacker_schedule,
            )
        )
        self.assertEqual([candidate.policy for candidate in selection.candidates], [DELAYED_FLOWING_TAKEOVER])
        self.assertEqual(selection.selected_policy, DELAYED_FLOWING_TAKEOVER)

    def test_no_delayed_policy_is_authorized_when_the_margin_is_insufficient(self) -> None:
        scenario = delayed_isolation_scenarios()["delayed_t1_margin_insufficient"]
        selection = select_recovery_policy(
            incident_from_context(
                scenario.context,
                require_continuous_delivery=True,
                attacker_schedule=scenario.attacker_schedule,
            )
        )
        self.assertIsNone(selection.selected_policy)
        self.assertEqual(len(selection.candidates), 1)
        self.assertEqual(selection.candidates[0].status.value, "NOT_COVERED_BY_CERTIFICATE")
