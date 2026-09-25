from __future__ import annotations

import os
import re
import unittest
from dataclasses import replace

from recovery_experiment.formal_problem import (
    ArtifactStatus,
    CertificateReviewStatus,
    ConstructionStatus,
    TheoremStatus,
    assess_incident_formal_problem,
    construct_formal_problem,
)
from recovery_experiment.intermediate_delay_formal import render_intermediate_delay_recovery_envelope
from recovery_experiment.model import AttackerAction, PlantParameters
from recovery_experiment.policies import (
    ScheduledPrimaryAttacker,
    TrustedDelayedIsolationFlowingBackupTakeoverPolicy,
)
from recovery_experiment.recovery_model_builder import (
    BuildStatus,
    IsolationMode,
    PhaseKind,
    build_recovery_problem,
)
from recovery_experiment.recovery_selection import (
    INTERMEDIATE_FLOWING_TAKEOVER,
    incident_from_context,
    select_recovery_policy,
)
from recovery_experiment.scenarios import context_for
from recovery_experiment.experiment import run_scenario


def _normalized(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _one_period_parameters() -> PlantParameters:
    return replace(
        PlantParameters(),
        isolation_delay=0.5,
        backup_startup_delay=1.5,
        transfer_recovery_deadline=1.5,
    )


def _two_period_parameters() -> PlantParameters:
    return replace(
        PlantParameters(),
        isolation_delay=1.0,
        backup_startup_delay=1.5,
        transfer_recovery_deadline=1.5,
    )


class RecoveryModelBuilderTests(unittest.TestCase):
    def test_reconstructs_immediate_and_two_period_canonical_games(self) -> None:
        immediate = build_recovery_problem(context_for(PlantParameters()))
        delayed = build_recovery_problem(context_for(_two_period_parameters()))
        self.assertEqual(immediate.status, BuildStatus.CONSTRUCTED)
        self.assertEqual(delayed.status, BuildStatus.CONSTRUCTED)
        self.assertEqual(immediate.spec.isolation_mode, IsolationMode.IMMEDIATE)
        self.assertEqual(delayed.spec.isolation_mode, IsolationMode.TWO_CONTROL_PERIOD)
        self.assertTrue(immediate.canonical_equivalent)
        self.assertTrue(delayed.canonical_equivalent)
        self.assertTrue(immediate.matching_verified_artifact)
        self.assertTrue(delayed.matching_verified_artifact)

    def test_two_period_phase_order_keeps_p1_effective_only_while_isolation_is_pending(self) -> None:
        generated = build_recovery_problem(context_for(_two_period_parameters()))
        self.assertEqual(
            [phase.kind for phase in generated.phases],
            [
                PhaseKind.ATTACKER_COMMAND,
                PhaseKind.ISOLATION_REQUEST,
                PhaseKind.ISOLATION_PENDING_EVOLUTION,
                PhaseKind.ATTACKER_COMMAND,
                PhaseKind.ISOLATION_PENDING_EVOLUTION,
                PhaseKind.EFFECTIVE_ISOLATION,
                PhaseKind.ATTACKER_COMMAND,
                PhaseKind.BACKUP_PENDING_EVOLUTION,
                PhaseKind.BACKUP_AVAILABLE,
                PhaseKind.POST_TAKEOVER_OPERATION,
            ],
        )
        pending = [phase for phase in generated.phases if phase.kind is PhaseKind.ISOLATION_PENDING_EVOLUTION]
        self.assertEqual([phase.duration for phase in pending], ["ControlPeriod", "ControlPeriod"])
        self.assertTrue(all(phase.primary_physically_effective for phase in pending))
        post_command = generated.phases[6]
        self.assertTrue(post_command.attacker_commandable)
        self.assertFalse(post_command.primary_physically_effective)

    def test_one_period_game_is_generated_with_derived_margins_but_no_artifact(self) -> None:
        generated = build_recovery_problem(context_for(_one_period_parameters()))
        self.assertEqual(generated.status, BuildStatus.CONSTRUCTED)
        self.assertEqual(generated.spec.isolation_mode, IsolationMode.ONE_CONTROL_PERIOD)
        self.assertFalse(generated.canonical_equivalent)
        self.assertFalse(generated.matching_verified_artifact)
        self.assertEqual(
            [phase.duration for phase in generated.phases if phase.kind is PhaseKind.ISOLATION_PENDING_EVOLUTION],
            ["ControlPeriod"],
        )
        self.assertIn(
            "x1 + (startupInflow - qprimary) * IsolationDelay >= L1",
            generated.spec.margins.as_tuple(),
        )
        self.assertEqual(
            generated.spec.margins.as_tuple(),
            (
                "x1 + startupInflow * StartupDelay <= H1",
                "x1 + (startupInflow - qprimary) * IsolationDelay >= L1",
                "x2 - startupWithdrawal * StartupDelay >= L2",
                "x2 + (qprimary - startupWithdrawal) * IsolationDelay <= H2",
            ),
        )
        self.assertIn("IsolationDelay = 1 * ControlPeriod", generated.envelope_text)
        self.assertIn("StartupDelay = 3 * ControlPeriod", generated.envelope_text)
        self.assertNotIn("}*", generated.envelope_text)

    def test_one_period_formal_problem_uses_its_reviewed_runtime_certificate(self) -> None:
        context = context_for(_one_period_parameters())
        construction = construct_formal_problem(context)
        assessment = assess_incident_formal_problem(context)
        self.assertEqual(construction.status, ConstructionStatus.CONSTRUCTED)
        self.assertEqual(construction.artifact_status, ArtifactStatus.MATCHING_VERIFIED_ARTIFACT_FOUND)
        self.assertTrue(construction.certificate_theorem_verified)
        self.assertEqual(construction.theorem_status, TheoremStatus.REVIEWED_VERIFIED)
        self.assertEqual(construction.certificate_review_status, CertificateReviewStatus.ISSUED)
        self.assertIsNotNone(construction.certificate_id)
        self.assertIsNotNone(assessment.certificate)
        self.assertTrue(assessment.certificate.covered)

    def test_one_period_selector_uses_only_its_own_reviewed_certificate(self) -> None:
        context = context_for(_one_period_parameters())
        selection = select_recovery_policy(
            incident_from_context(
                context,
                require_continuous_delivery=True,
                attacker_schedule=(AttackerAction.FORCE_PRIMARY_ON,),
            )
        )
        self.assertEqual([candidate.policy for candidate in selection.candidates], [INTERMEDIATE_FLOWING_TAKEOVER])
        self.assertEqual(selection.selected_policy, INTERMEDIATE_FLOWING_TAKEOVER)
        self.assertTrue(selection.candidates[0].certificate.covered)

    def test_one_period_simulator_timing_matches_generated_phase_authority(self) -> None:
        context = context_for(_one_period_parameters())
        result = run_scenario(
            "one_period_builder_timing",
            context.plant,
            ScheduledPrimaryAttacker((AttackerAction.FORCE_PRIMARY_ON,)),
            TrustedDelayedIsolationFlowingBackupTakeoverPolicy(),
            initial_state=context.current_state,
        )
        first, second, third, fourth = result.records[:4]
        self.assertTrue(first.isolation_pending_during_interval)
        self.assertTrue(first.p1_effective_state)
        self.assertEqual(first.q1, context.plant.primary_capacity)
        self.assertTrue(second.isolation_effective_during_interval)
        self.assertFalse(second.p1_effective_state)
        self.assertEqual(second.q1, 0.0)
        self.assertEqual(third.q2, 0.0)
        self.assertEqual(fourth.q2, context.plant.backup_capacity)
        self.assertEqual(result.final_state.recovery_established_at, 1.5)

    def test_unsupported_delay_is_not_rounded_to_a_builder_schedule(self) -> None:
        unsupported = replace(_one_period_parameters(), isolation_delay=0.75)
        generated = build_recovery_problem(context_for(unsupported))
        self.assertEqual(generated.status, BuildStatus.UNSUPPORTED_CONFIGURATION)
        self.assertFalse(generated.matching_verified_artifact)

    def test_missing_trusted_isolation_is_rejected_before_composition(self) -> None:
        context = context_for(_one_period_parameters())
        malformed = replace(
            context,
            trusted_actuators=frozenset({"P2_command", "upstream_gate", "demand_gate"}),
        )
        generated = build_recovery_problem(malformed)
        self.assertEqual(generated.status, BuildStatus.INVALID_CONTEXT)
        self.assertIsNone(generated.envelope_text)

    def test_builder_output_is_reproducible(self) -> None:
        context = context_for(_two_period_parameters())
        first, second = build_recovery_problem(context), build_recovery_problem(context)
        self.assertEqual(first.as_dict(), second.as_dict())

    @unittest.skipUnless(os.environ.get("RUN_CLEO_REGRESSION") == "1", "set RUN_CLEO_REGRESSION=1")
    def test_generated_intermediate_game_parses_and_new_proof_attempt_succeeds(self) -> None:
        from recovery_experiment.formal import FormalStatus
        from recovery_experiment.verify_intermediate_delay_recovery import verify_intermediate_delay_theorem
        from cleo.envelope_format import parse_envelope
        from cleo.parser import parse_defs_from_string, parse_formula_from_string, parse_game_from_string

        text = render_intermediate_delay_recovery_envelope().envelope_text
        parsed = parse_envelope(text)
        parse_defs_from_string(parsed.defs_str)
        parse_formula_from_string(parsed.precondition_str)
        parse_formula_from_string(parsed.postcondition_str)
        parse_game_from_string(parsed.game_str)
        self.assertEqual(verify_intermediate_delay_theorem().status, FormalStatus.VERIFIED)
