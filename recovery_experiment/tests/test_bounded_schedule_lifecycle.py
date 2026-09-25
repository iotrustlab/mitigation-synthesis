from __future__ import annotations

import os
import unittest
from dataclasses import replace

from recovery_experiment.bounded_delay_proof_profile import generated_profile
from recovery_experiment.formal_problem import (
    ArtifactStatus,
    CertificateReviewStatus,
    TheoremStatus,
    assess_incident_formal_problem,
)
from recovery_experiment.intermediate_delay_certificate import check_intermediate_delay_recovery
from recovery_experiment.intermediate_delay_formal import (
    INTERMEDIATE_DELAY_PLANT_MODEL_ID,
    INTERMEDIATE_DELAY_POLICY_ID,
)
from recovery_experiment.model import AttackerAction, PlantParameters
from recovery_experiment.policies import (
    ScheduledPrimaryAttacker,
    TrustedDelayedIsolationFlowingBackupTakeoverPolicy,
)
from recovery_experiment.recovery_model_builder import (
    BuildStatus,
    BoundedIsolationSchedule,
    PhaseKind,
    build_recovery_problem,
)
from recovery_experiment.recovery_selection import incident_from_context, select_recovery_policy
from recovery_experiment.experiment import run_scenario
from recovery_experiment.scenarios import context_for


def _parameters(isolation_periods: int, startup_periods: int) -> PlantParameters:
    return replace(
        PlantParameters(),
        isolation_delay=isolation_periods * 0.5,
        backup_startup_delay=startup_periods * 0.5,
        transfer_recovery_deadline=startup_periods * 0.5,
    )


class BoundedScheduleLifecycleTests(unittest.TestCase):
    def test_existing_and_new_integer_schedule_shapes_are_deterministic(self) -> None:
        for isolation_periods, startup_periods in ((0, 2), (1, 3), (2, 3), (3, 4), (3, 5)):
            context = context_for(_parameters(isolation_periods, startup_periods))
            first = build_recovery_problem(context)
            second = build_recovery_problem(context)
            self.assertEqual(first.status, BuildStatus.CONSTRUCTED)
            self.assertEqual(first.as_dict(), second.as_dict())
            self.assertEqual(first.spec.schedule.isolation_periods, isolation_periods)
            self.assertEqual(first.spec.schedule.startup_periods, startup_periods)

    def test_noncanonical_immediate_schedule_keeps_its_exact_integer_timing(self) -> None:
        generated = build_recovery_problem(context_for(_parameters(0, 3)))
        self.assertEqual(generated.status, BuildStatus.CONSTRUCTED)
        self.assertFalse(generated.canonical_equivalent)
        self.assertIn("IsolationDelay = 0 * ControlPeriod", generated.envelope_text)
        self.assertIn("StartupDelay = 3 * ControlPeriod", generated.envelope_text)

    def test_three_period_schedule_has_three_effective_attacker_intervals(self) -> None:
        generated = build_recovery_problem(context_for(_parameters(3, 4)))
        self.assertEqual(
            [phase.kind for phase in generated.phases].count(PhaseKind.ISOLATION_PENDING_EVOLUTION), 3
        )
        self.assertEqual(
            [phase.kind for phase in generated.phases].count(PhaseKind.ATTACKER_COMMAND), 4
        )
        pending = [phase for phase in generated.phases if phase.kind is PhaseKind.ISOLATION_PENDING_EVOLUTION]
        self.assertTrue(all(phase.primary_physically_effective for phase in pending))
        attacker_effective = [
            phase
            for phase in generated.phases
            if phase.kind is PhaseKind.ATTACKER_COMMAND and phase.primary_physically_effective
        ]
        self.assertEqual(len(attacker_effective), 3)
        self.assertEqual(
            [phase.name for phase in generated.phases if phase.kind is PhaseKind.BACKUP_PENDING_EVOLUTION],
            ["backup_pending_interval_1"],
        )
        effective = next(phase for phase in generated.phases if phase.kind is PhaseKind.EFFECTIVE_ISOLATION)
        self.assertFalse(effective.primary_physically_effective)

    def test_generated_profile_has_one_pending_invariant_per_attacker_interval(self) -> None:
        generated = build_recovery_problem(context_for(_parameters(3, 5)))
        self.assertEqual(
            [phase.name for phase in generated.phases if phase.kind is PhaseKind.BACKUP_PENDING_EVOLUTION],
            ["backup_pending_interval_1", "backup_pending_interval_2"],
        )
        profile = generated_profile(BoundedIsolationSchedule(0.5, 3, 5))
        self.assertEqual(
            profile.invariant_names,
            (
                "isolation_pending_phase_1",
                "isolation_pending_phase_2",
                "isolation_pending_phase_3",
                "backup_pending_phase_1",
                "backup_pending_phase_2",
                "operation_phase",
            ),
        )

    def test_noncanonical_immediate_profile_has_no_attacker_pending_invariant(self) -> None:
        profile = generated_profile(BoundedIsolationSchedule(0.5, 0, 3))
        self.assertEqual(profile.invariant_names, ("backup_pending_phase", "operation_phase"))

    def test_invalid_or_unaligned_schedule_is_not_rounded(self) -> None:
        equal_delays = build_recovery_problem(context_for(_parameters(3, 3)))
        unaligned = build_recovery_problem(
            context_for(replace(_parameters(3, 4), isolation_delay=1.75))
        )
        self.assertEqual(equal_delays.status, BuildStatus.UNSUPPORTED_CONFIGURATION)
        self.assertEqual(unaligned.status, BuildStatus.UNSUPPORTED_CONFIGURATION)

    def test_new_recorded_verified_schedule_is_not_runtime_authorized_before_review(self) -> None:
        context = context_for(_parameters(3, 4))
        assessment = assess_incident_formal_problem(context)
        selection = select_recovery_policy(
            incident_from_context(
                context,
                require_continuous_delivery=True,
                attacker_schedule=(
                    AttackerAction.FORCE_PRIMARY_ON,
                    AttackerAction.FORCE_PRIMARY_ON,
                    AttackerAction.FORCE_PRIMARY_ON,
                ),
            )
        )
        self.assertEqual(assessment.construction.artifact_status, ArtifactStatus.FORMAL_PROBLEM_UNVERIFIED)
        self.assertEqual(assessment.construction.theorem_status, TheoremStatus.VERIFIED)
        self.assertEqual(assessment.construction.certificate_review_status, CertificateReviewStatus.REVIEW_REQUIRED)
        self.assertIsNone(assessment.certificate)
        self.assertEqual(selection.candidates, ())

    def test_one_period_certificate_does_not_cover_another_schedule(self) -> None:
        context = context_for(_parameters(1, 4))
        projected = replace(
            context,
            plant_model_id=INTERMEDIATE_DELAY_PLANT_MODEL_ID,
            recovery_policy_id=INTERMEDIATE_DELAY_POLICY_ID,
        )
        coverage = check_intermediate_delay_recovery(
            projected,
            attacker_schedule=(AttackerAction.FORCE_PRIMARY_ON,),
        )
        self.assertFalse(coverage.covered)
        self.assertIn("backup startup delay must equal exactly three control periods", coverage.reasons)

    def test_simulator_matches_three_period_authority_and_backup_timing(self) -> None:
        context = context_for(_parameters(3, 4))
        result = run_scenario(
            "three_period_timing",
            context.plant,
            ScheduledPrimaryAttacker((AttackerAction.FORCE_PRIMARY_ON,) * 3),
            TrustedDelayedIsolationFlowingBackupTakeoverPolicy(),
            initial_state=context.current_state,
        )
        first, second, third, fourth, fifth = result.records[:5]
        self.assertTrue(all(record.p1_effective_state for record in (first, second, third)))
        self.assertTrue(all(record.isolation_pending_during_interval for record in (first, second, third)))
        self.assertFalse(fourth.p1_effective_state)
        self.assertEqual(fourth.q1, 0.0)
        self.assertEqual(fourth.q2, 0.0)
        self.assertEqual(fifth.q2, context.plant.backup_capacity)
        self.assertEqual(result.final_state.recovery_established_at, 2.0)

    @unittest.skipUnless(os.environ.get("RUN_CLEO_REGRESSION") == "1", "set RUN_CLEO_REGRESSION=1")
    def test_new_bounded_schedules_parse_and_prove(self) -> None:
        from recovery_experiment.formal import FormalStatus
        from recovery_experiment.verify_bounded_delay_recovery import verify_bounded_delay_theorem

        for schedule in (BoundedIsolationSchedule(0.5, 3, 4), BoundedIsolationSchedule(0.5, 3, 5)):
            self.assertEqual(verify_bounded_delay_theorem(schedule).status, FormalStatus.VERIFIED)
