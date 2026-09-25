from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from recovery_experiment.context import ContextValidationError, RecoveryContext
from recovery_experiment.experiment import default_scenarios, run_scenario, write_trace
from recovery_experiment.formal import FormalStatus, assess_takeover_readiness, render_recovery_envelope
from recovery_experiment.model import (
    AttackerAction,
    DefenderAction,
    ModelValidationError,
    PlantParameters,
    PlantState,
    TwoTankPlant,
)
from recovery_experiment.policies import NoRecoveryPolicy, PersistentPrimaryAttacker, TrustedBackupTakeoverPolicy
from recovery_experiment.scenarios import context_for, named_contexts
from recovery_experiment.timed_formal import assess_timed_takeover_readiness, render_timed_recovery_envelope


class PlantSimulationTests(unittest.TestCase):
    def test_normal_operation_is_equilibrium(self) -> None:
        normal = default_scenarios(seed=19)["normal_operation"]
        self.assertTrue(normal.safe)
        self.assertEqual((normal.final_state.x1, normal.final_state.x2), (7.0, 6.0))

    def test_primary_disruption_moves_levels_in_expected_direction(self) -> None:
        attacked = default_scenarios()["primary_compromise_no_recovery"]
        self.assertGreater(attacked.final_state.x1, 7.0)
        self.assertLess(attacked.final_state.x2, 6.0)
        self.assertFalse(attacked.safe)

    def test_takeover_restores_service_after_startup(self) -> None:
        takeover = default_scenarios()["trusted_backup_takeover"]
        self.assertTrue(takeover.safe)
        self.assertTrue(takeover.service_satisfied_after_deadline)
        self.assertTrue(any(row.p2_effective_state for row in takeover.records))

    def test_isolation_blocks_a_continued_primary_on_attack(self) -> None:
        plant = TwoTankPlant(PlantParameters())
        plant.step(AttackerAction.FORCE_PRIMARY_ON, DefenderAction.START_TAKEOVER)
        # The attacker has control of the command bit, but not the separate isolator.
        row = plant.step(AttackerAction.FORCE_PRIMARY_ON, DefenderAction.START_TAKEOVER)
        self.assertTrue(row.primary_path_isolated)
        self.assertTrue(row.p1_command)
        self.assertFalse(row.p1_effective_state)
        self.assertEqual(row.q1, 0.0)

    def test_backup_delay_is_not_instantaneous(self) -> None:
        plant = TwoTankPlant(PlantParameters(backup_startup_delay=1.0))
        first = plant.step(AttackerAction.FORCE_PRIMARY_OFF, DefenderAction.START_TAKEOVER)
        second = plant.step(AttackerAction.FORCE_PRIMARY_OFF, DefenderAction.START_TAKEOVER)
        third = plant.step(AttackerAction.FORCE_PRIMARY_OFF, DefenderAction.START_TAKEOVER)
        self.assertFalse(first.p2_effective_state)
        self.assertFalse(second.p2_effective_state)
        self.assertTrue(third.p2_effective_state)

    def test_attacker_stays_active_only_for_its_configured_interval(self) -> None:
        parameters = PlantParameters(horizon=2.0)
        result = run_scenario(
            "bounded_attack",
            parameters,
            PersistentPrimaryAttacker(active_until=1.0),
            NoRecoveryPolicy(),
        )
        self.assertEqual(
            [row.attacker_action for row in result.records],
            ["force_primary_off", "force_primary_off", "noop", "noop"],
        )


class ContextAndFormalTests(unittest.TestCase):
    def test_valid_context_is_accepted(self) -> None:
        context = named_contexts()["baseline_feasible"]
        context.validate()

    def test_unknown_component_is_rejected(self) -> None:
        context = named_contexts()["baseline_feasible"]
        malformed = replace(context, trusted_actuators=context.trusted_actuators | {"not_a_component"})
        with self.assertRaises(ContextValidationError):
            malformed.validate()

    def test_resource_mismatch_is_rejected(self) -> None:
        context = named_contexts()["baseline_feasible"]
        malformed = replace(context, available_recovery_resources={"backup_capacity": 99.0, "primary_isolation": True})
        with self.assertRaises(ContextValidationError):
            malformed.validate()

    def test_missing_recovery_resource_and_untrusted_control_are_rejected(self) -> None:
        context = named_contexts()["baseline_feasible"]
        missing = replace(context, available_recovery_resources={"primary_isolation": True})
        untrusted = replace(context, trusted_actuators=frozenset({"P2_command"}))
        with self.assertRaises(ContextValidationError):
            missing.validate()
        with self.assertRaises(ContextValidationError):
            untrusted.validate()

    def test_invalid_plant_timing_is_rejected(self) -> None:
        with self.assertRaises(ModelValidationError):
            PlantParameters(control_period=0.0).validate()

    def test_invalid_capacity_is_not_reported_as_verified(self) -> None:
        context = named_contexts()["insufficient_backup_capacity"]
        self.assertEqual(assess_takeover_readiness(context).status, FormalStatus.REJECTED_CAPACITY)
        from recovery_experiment.verify_recovery import verify_context

        self.assertEqual(verify_context(context).status, FormalStatus.REJECTED_CAPACITY)

    def test_timed_template_rejects_late_startup_without_claiming_global_infeasibility(self) -> None:
        context = named_contexts()["startup_deadline_inadmissible"]
        self.assertEqual(
            assess_timed_takeover_readiness(context).status,
            FormalStatus.REJECTED_DEADLINE,
        )
        from recovery_experiment.verify_timed_recovery import verify_timed_context

        self.assertEqual(verify_timed_context(context).status, FormalStatus.REJECTED_DEADLINE)

    def test_timed_template_rejects_insufficient_actual_delivery(self) -> None:
        context = named_contexts()["insufficient_backup_capacity"]
        self.assertEqual(
            assess_timed_takeover_readiness(context).status,
            FormalStatus.REJECTED_CAPACITY,
        )

    def test_timed_template_marks_delayed_isolation_as_unsupported(self) -> None:
        baseline = named_contexts()["baseline_feasible"]
        delayed = context_for(replace(baseline.plant, isolation_delay=0.5))
        self.assertEqual(
            assess_timed_takeover_readiness(delayed).status,
            FormalStatus.UNSUPPORTED_TEMPLATE,
        )

    def test_timed_template_marks_ode_domain_assumption_as_unsupported(self) -> None:
        baseline = named_contexts()["baseline_feasible"]
        nonphysical_lower_bound = context_for(replace(baseline.plant, low_t1=-1.0))
        self.assertEqual(
            assess_timed_takeover_readiness(nonphysical_lower_bound).status,
            FormalStatus.UNSUPPORTED_TEMPLATE,
        )

    def test_malformed_context_is_distinguished_from_an_unsupported_template(self) -> None:
        baseline = named_contexts()["baseline_feasible"]
        malformed = replace(baseline, trusted_actuators=frozenset({"P2_command"}))
        from recovery_experiment.verify_timed_recovery import verify_timed_context

        self.assertEqual(verify_timed_context(malformed).status, FormalStatus.INVALID_CONTEXT)

    def test_generated_envelope_parses_when_cleo_is_available(self) -> None:
        try:
            from cleo.envelope_format import parse_envelope
            from cleo.parser import parse_defs_from_string, parse_formula_from_string, parse_game_from_string
        except ImportError:
            self.skipTest("CLEO is not installed in this interpreter")
        instance = render_recovery_envelope(named_contexts()["baseline_feasible"])
        spec = parse_envelope(instance.envelope_text)
        parse_defs_from_string(spec.defs_str)
        parse_formula_from_string(spec.precondition_str)
        parse_formula_from_string(spec.postcondition_str)
        parse_game_from_string(spec.game_str)
        static_spec = parse_envelope(
            (Path(__file__).resolve().parents[1] / "recovery_takeover.envelope").read_text()
        )
        parse_defs_from_string(static_spec.defs_str)
        parse_formula_from_string(static_spec.precondition_str)
        parse_formula_from_string(static_spec.postcondition_str)
        parse_game_from_string(static_spec.game_str)

        timed = render_timed_recovery_envelope(named_contexts()["baseline_feasible"])
        timed_spec = parse_envelope(timed.envelope_text)
        parse_defs_from_string(timed_spec.defs_str)
        parse_formula_from_string(timed_spec.precondition_str)
        parse_formula_from_string(timed_spec.postcondition_str)
        parse_game_from_string(timed_spec.game_str)
        timed_static_spec = parse_envelope(
            (Path(__file__).resolve().parents[1] / "timed_recovery_takeover.envelope").read_text()
        )
        parse_defs_from_string(timed_static_spec.defs_str)
        parse_formula_from_string(timed_static_spec.precondition_str)
        parse_formula_from_string(timed_static_spec.postcondition_str)
        parse_game_from_string(timed_static_spec.game_str)

    def test_formal_template_keeps_attacker_and_independent_isolator(self) -> None:
        text = render_recovery_envelope(named_contexts()["baseline_feasible"]).envelope_text
        self.assertIn("{ p1 := 0; }", text)
        self.assertIn("{ p1 := 1; }", text)
        self.assertIn("}^@;", text)
        self.assertIn("isolated := 1", text)
        self.assertIn("(1-isolated) * p1 * qprimary", text)
        self.assertIn("interventionBudget - (isolationCost + backupCost)", text)

    def test_timed_template_has_strict_timing_delivery_and_operation_obligations(self) -> None:
        text = render_timed_recovery_envelope(named_contexts()["baseline_feasible"]).envelope_text
        static_text = (Path(__file__).resolve().parents[1] / "timed_recovery_takeover.envelope").read_text()
        self.assertEqual(text, static_text)
        self.assertIn("qdelivered = q2 & qdelivered = qd & qdelivered >= qmin", text)
        self.assertIn("recoveryClock <= RecoveryDeadline", text)
        self.assertIn("? startupClock >= StartupDelay;", text)
        self.assertIn("? operationClock >= T;", text)
        self.assertIn("operation_ode:", text)
        self.assertIn("T > 0", text)
        self.assertNotIn("}*", text)
        startup_segment = text.split("startup_ode:", 1)[1].split("? startupClock", 1)[0]
        self.assertNotIn("}^@", startup_segment)

    def test_timed_template_retains_attacker_control_but_requires_independent_isolation(self) -> None:
        text = render_timed_recovery_envelope(named_contexts()["baseline_feasible"]).envelope_text
        self.assertGreaterEqual(text.count("{ p1 := 1; }"), 2)
        self.assertGreaterEqual(text.count("isolated := 1;"), 2)
        self.assertIn("q1 := 0;", text)
        self.assertIn("q1 = (1-isolated) * p1 * qprimary", text)


class ReproducibilityTests(unittest.TestCase):
    def test_same_seed_yields_same_trace_and_metadata(self) -> None:
        one = default_scenarios(seed=101)["trusted_backup_takeover"]
        two = default_scenarios(seed=101)["trusted_backup_takeover"]
        self.assertEqual([row.as_dict() for row in one.records], [row.as_dict() for row in two.records])
        with tempfile.TemporaryDirectory() as directory:
            path = write_trace(one, Path(directory) / "trace.json")
            payload = json.loads(path.read_text())
        self.assertEqual(payload["metadata"]["seed"], 101)
        self.assertIn("parameters", payload["metadata"])
        self.assertEqual(len(payload["records"]), len(one.records))


class OptionalIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("RUN_CLEO_REGRESSION") == "1", "set RUN_CLEO_REGRESSION=1")
    def test_baseline_recovery_is_verified_only_after_cleo_discharges_obligations(self) -> None:
        from recovery_experiment.verify_recovery import verify_context

        result = verify_context(named_contexts()["baseline_feasible"])
        self.assertEqual(result.status, FormalStatus.VERIFIED, result.reason)

    @unittest.skipUnless(os.environ.get("RUN_CLEO_REGRESSION") == "1", "set RUN_CLEO_REGRESSION=1")
    def test_timed_recovery_contract_discharges_all_nonvacuous_milestones(self) -> None:
        from recovery_experiment.verify_timed_recovery import verify_timed_context

        result = verify_timed_context(named_contexts()["baseline_feasible"])
        self.assertEqual(result.status, FormalStatus.VERIFIED, result.reason)
        self.assertTrue(all(milestone["passed"] for milestone in result.milestones.values()))

    @unittest.skipUnless(os.environ.get("RUN_CLEO_REGRESSION") == "1", "set RUN_CLEO_REGRESSION=1")
    def test_canonical_phase1_proof_remains_a_regression_baseline(self) -> None:
        root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [sys.executable, "water_attack.py"], cwd=root, text=True, capture_output=True, timeout=180
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
