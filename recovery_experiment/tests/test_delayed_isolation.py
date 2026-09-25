from __future__ import annotations

import os
import unittest
from dataclasses import replace
from pathlib import Path

from recovery_experiment.certificate import CertificateStatus
from recovery_experiment.delayed_isolation_evaluation import (
    delayed_isolation_scenarios,
    evaluate_delayed_isolation_scenarios,
)
from recovery_experiment.delayed_isolation_formal import (
    DELAYED_ISOLATION_MODEL_ID,
    DELAYED_ISOLATION_POLICY_ID,
    render_delayed_isolation_recovery_envelope,
)
from recovery_experiment.formal_problem import (
    ArtifactStatus,
    CertificateReviewStatus,
    ConstructionStatus,
    IncidentIsolationMode,
    TheoremStatus,
    assess_incident_formal_problem,
    construct_formal_problem,
)
from recovery_experiment.experiment import run_scenario
from recovery_experiment.model import AttackerAction, PlantParameters, PlantState
from recovery_experiment.policies import (
    ScheduledPrimaryAttacker,
    TrustedDelayedIsolationFlowingBackupTakeoverPolicy,
)


class DelayedIsolationFormalTests(unittest.TestCase):
    def test_static_artifact_matches_delayed_renderer(self) -> None:
        expected = render_delayed_isolation_recovery_envelope().envelope_text
        static = (Path(__file__).resolve().parents[1] / "delayed_isolation_recovery_takeover.envelope").read_text()
        self.assertEqual(static, expected)

    def test_game_encodes_two_effective_attacker_periods_and_mandatory_phases(self) -> None:
        text = render_delayed_isolation_recovery_envelope().envelope_text
        self.assertEqual(text.count("{ p1 := 0; q1 := 0; }"), 2)
        self.assertIn("IsolationDelay = 2 * ControlPeriod", text)
        self.assertIn("StartupDelay = 3 * ControlPeriod", text)
        self.assertIn("? isolationClock >= ControlPeriod;", text)
        self.assertIn("? isolationClock >= IsolationDelay;", text)
        self.assertIn("isolated := 1;\n        q1 := 0;", text)
        self.assertIn("{ p1 := 1; }", text)
        self.assertIn("? startupClock >= StartupDelay;", text)
        self.assertIn("? operationClock >= T;", text)
        self.assertNotIn("}*", text)

    def test_safety_is_not_hidden_in_ode_evolution_domains(self) -> None:
        text = render_delayed_isolation_recovery_envelope().envelope_text
        for ode_name in (
            "isolation_phase_one:",
            "isolation_phase_two:",
            "backup_pending_phase:",
            "operation_phase:",
        ):
            ode = text.split(ode_name, 1)[1].split("};", 1)[0]
            self.assertNotIn("L1 <= x1", ode)
            self.assertNotIn("x1 <= H1", ode)
            self.assertNotIn("L2 <= x2", ode)
            self.assertNotIn("x2 <= H2", ode)


class DelayedIsolationSimulatorTests(unittest.TestCase):
    @staticmethod
    def _parameters() -> PlantParameters:
        return replace(
            PlantParameters(),
            isolation_delay=1.0,
            backup_startup_delay=1.5,
            transfer_recovery_deadline=1.5,
        )

    def _run(self, scenario_name: str):
        scenario = delayed_isolation_scenarios()[scenario_name]
        self.assertIsNotNone(scenario.attacker_schedule)
        return run_scenario(
            scenario_name,
            scenario.context.plant,
            ScheduledPrimaryAttacker(scenario.attacker_schedule or ()),
            TrustedDelayedIsolationFlowingBackupTakeoverPolicy(),
            initial_state=scenario.context.current_state,
        )

    def test_command_pending_and_effective_states_follow_the_explicit_schedule(self) -> None:
        result = self._run("delayed_safe_command_change")
        first, second, third, fourth = result.records[:4]
        self.assertTrue(first.isolation_commanded)
        self.assertTrue(first.isolation_pending_during_interval)
        self.assertFalse(first.isolation_effective_during_interval)
        self.assertEqual(first.q1, 0.0)
        self.assertTrue(second.isolation_pending_during_interval)
        self.assertTrue(second.p1_effective_state)
        self.assertEqual(second.q1, 1.5)
        self.assertTrue(third.isolation_effective_during_interval)
        self.assertFalse(third.p1_effective_state)
        self.assertEqual(third.q1, 0.0)
        self.assertTrue(third.backup_start_pending_during_interval)
        self.assertTrue(fourth.p2_effective_state)
        self.assertEqual(fourth.q2, 1.5)
        self.assertEqual(result.final_state.recovery_established_at, 1.5)

    def test_p1_off_and_p1_on_threaten_different_tank_bounds(self) -> None:
        t1 = self._run("delayed_t1_margin_insufficient")
        t2 = self._run("delayed_t2_on_threat")
        self.assertFalse(t1.safe)
        self.assertGreater(t1.records[2].x1, t1.parameters.high_t1)
        self.assertFalse(t2.safe)
        self.assertGreater(t2.records[1].x2, t2.parameters.high_t2)

    def test_insufficient_backup_can_preserve_short_term_delivery_but_not_safety(self) -> None:
        result = self._run("delayed_insufficient_backup")
        self.assertFalse(result.safe)
        self.assertTrue(all(record.q_delivered >= result.parameters.min_service_flow for record in result.records))
        self.assertEqual(result.records[3].q2, 1.0)

    def test_time_indexed_bounds_hold_for_every_two_interval_attacker_schedule(self) -> None:
        initial = PlantState(x1=7.0, x2=6.0)
        parameters = self._parameters()
        schedules = (
            (AttackerAction.FORCE_PRIMARY_OFF, AttackerAction.FORCE_PRIMARY_OFF),
            (AttackerAction.FORCE_PRIMARY_OFF, AttackerAction.FORCE_PRIMARY_ON),
            (AttackerAction.FORCE_PRIMARY_ON, AttackerAction.FORCE_PRIMARY_OFF),
            (AttackerAction.FORCE_PRIMARY_ON, AttackerAction.FORCE_PRIMARY_ON),
        )
        for schedule in schedules:
            with self.subTest(schedule=schedule):
                result = run_scenario(
                    "time_indexed_bounds",
                    parameters,
                    ScheduledPrimaryAttacker(schedule),
                    TrustedDelayedIsolationFlowingBackupTakeoverPolicy(),
                    initial_state=initial,
                )
                for record in result.records[:2]:
                    elapsed = record.timestamp
                    self.assertGreaterEqual(record.x1 + 1e-12, initial.x1 + (1.0 - 1.5) * elapsed)
                    self.assertLessEqual(record.x1 - 1e-12, initial.x1 + 1.0 * elapsed)
                    self.assertGreaterEqual(record.x2 + 1e-12, initial.x2 - 1.2 * elapsed)
                    self.assertLessEqual(record.x2 - 1e-12, initial.x2 + (1.5 - 1.2) * elapsed)

    def test_near_boundary_states_preserve_safety_for_their_respective_worst_cases(self) -> None:
        parameters = self._parameters()
        boundary_cases = (
            ("p1_off", PlantState(x1=9.49, x2=4.81), AttackerAction.FORCE_PRIMARY_OFF),
            ("p1_on", PlantState(x1=4.51, x2=8.69), AttackerAction.FORCE_PRIMARY_ON),
        )
        for name, state, action in boundary_cases:
            with self.subTest(case=name):
                result = run_scenario(
                    name,
                    parameters,
                    ScheduledPrimaryAttacker((action, action)),
                    TrustedDelayedIsolationFlowingBackupTakeoverPolicy(),
                    initial_state=state,
                )
                self.assertTrue(result.safe)
                self.assertTrue(all(record.safety_status == "safe" for record in result.records[:3]))


class DelayedIsolationConstructionTests(unittest.TestCase):
    def test_immediate_and_delayed_incidents_construct_different_formal_models(self) -> None:
        scenarios = delayed_isolation_scenarios()
        immediate = construct_formal_problem(scenarios["immediate_baseline"].context)
        delayed = construct_formal_problem(scenarios["delayed_safe_command_change"].context)
        self.assertEqual(immediate.status, ConstructionStatus.CONSTRUCTED)
        self.assertEqual(immediate.isolation_mode, IncidentIsolationMode.IMMEDIATE)
        self.assertTrue(immediate.certificate_theorem_verified)
        self.assertEqual(delayed.status, ConstructionStatus.CONSTRUCTED)
        self.assertEqual(delayed.isolation_mode, IncidentIsolationMode.DELAYED)
        self.assertEqual(delayed.formal_model_id, DELAYED_ISOLATION_MODEL_ID)
        self.assertEqual(delayed.recovery_policy_id, DELAYED_ISOLATION_POLICY_ID)
        self.assertTrue(delayed.certificate_theorem_verified)
        self.assertEqual(delayed.certificate_id, "two-tank-flowing-takeover-delayed-isolation-v1")

    def test_delayed_construction_uses_its_matching_certificate(self) -> None:
        context = delayed_isolation_scenarios()["delayed_safe_command_change"].context
        assessment = assess_incident_formal_problem(context)
        self.assertIsNotNone(assessment.certificate)
        self.assertEqual(assessment.certificate.status, CertificateStatus.COVERED_BY_CERTIFICATE)
        self.assertTrue(assessment.certificate.covered)
        self.assertEqual(
            assessment.certificate.certificate_id,
            "two-tank-flowing-takeover-delayed-isolation-v1",
        )

    def test_unreviewed_timing_and_missing_isolation_are_not_authorized(self) -> None:
        scenarios = delayed_isolation_scenarios()
        timing = construct_formal_problem(scenarios["delayed_timing_outside_family"].context)
        inadequate_backup = construct_formal_problem(scenarios["delayed_insufficient_backup"].context)
        missing = construct_formal_problem(scenarios["delayed_missing_isolation"].context)
        self.assertEqual(timing.status, ConstructionStatus.CONSTRUCTED)
        self.assertEqual(timing.isolation_mode, IncidentIsolationMode.DELAYED)
        self.assertIsNone(timing.certificate_id)
        self.assertFalse(timing.certificate_theorem_verified)
        self.assertEqual(timing.artifact_status, ArtifactStatus.FORMAL_PROBLEM_UNVERIFIED)
        self.assertEqual(timing.theorem_status, TheoremStatus.UNVERIFIED)
        self.assertEqual(timing.certificate_review_status, CertificateReviewStatus.REVIEW_REQUIRED)
        self.assertEqual(inadequate_backup.status, ConstructionStatus.UNSUPPORTED_CONFIGURATION)
        self.assertIn("qbackup >= qmin", inadequate_backup.reasons[0])
        self.assertEqual(missing.status, ConstructionStatus.INVALID_CONTEXT)
        self.assertIsNone(missing.isolation_mode)

    def test_evaluation_is_reproducible_except_for_latency(self) -> None:
        first = evaluate_delayed_isolation_scenarios()
        second = evaluate_delayed_isolation_scenarios()
        self.assertEqual(first["scope"], second["scope"])
        for name, first_case in first["scenarios"].items():
            second_case = second["scenarios"][name]
            self.assertEqual(first_case["description"], second_case["description"])
            self.assertEqual(first_case["attacker_schedule"], second_case["attacker_schedule"])
            self.assertEqual(first_case["formal_assessment"]["construction"], second_case["formal_assessment"]["construction"])
            first_certificate = first_case["formal_assessment"]["certificate"]
            second_certificate = second_case["formal_assessment"]["certificate"]
            if first_certificate is None or second_certificate is None:
                self.assertEqual(first_certificate, second_certificate)
            else:
                self.assertEqual(first_certificate["status"], second_certificate["status"])
                self.assertEqual(first_certificate["covered"], second_certificate["covered"])
                self.assertEqual(first_certificate["reasons"], second_certificate["reasons"])
                self.assertEqual(first_certificate["certificate_id"], second_certificate["certificate_id"])
            self.assertEqual(first_case["selected_recovery_policy"], second_case["selected_recovery_policy"])
            self.assertEqual(first_case["simulation"], second_case["simulation"])


class OptionalDelayedIsolationIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("RUN_CLEO_REGRESSION") == "1", "set RUN_CLEO_REGRESSION=1")
    def test_complete_delayed_isolation_theorem_is_verified(self) -> None:
        from recovery_experiment.formal import FormalStatus
        from recovery_experiment.verify_delayed_isolation_recovery import verify_delayed_isolation_theorem

        result = verify_delayed_isolation_theorem()
        self.assertEqual(result.status, FormalStatus.VERIFIED, result.reason)
        self.assertTrue(all(milestone["passed"] for milestone in result.milestones.values()))
