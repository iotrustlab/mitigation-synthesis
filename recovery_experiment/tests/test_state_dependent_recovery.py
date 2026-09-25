from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from recovery_experiment.certificate import CertificateStatus, check_certified_recovery
from recovery_experiment.state_dependent_certificate import (
    TRUSTED_MANIFEST_SHA256,
    check_state_dependent_recovery,
)
from recovery_experiment.state_dependent_concrete import render_state_dependent_context_envelope
from recovery_experiment.state_dependent_evaluation import (
    controlled_hold_baseline_context,
    evaluate_state_dependent_workflows,
    state_dependent_evaluation_contexts,
)
from recovery_experiment.state_dependent_formal import render_state_dependent_recovery_envelope


class StateDependentSimulatorTests(unittest.TestCase):
    def test_flowing_startup_uses_storage_for_actual_delivery(self) -> None:
        report = evaluate_state_dependent_workflows()
        record = report["flowing_startup_contexts"]["safe_recoverable"]
        startup = record["simulation"]["startup_trace"]
        self.assertEqual(len(startup), 2)
        for row in startup:
            self.assertEqual(row["q_in"], 1.0)
            self.assertEqual(row["q1"], 0.0)
            self.assertEqual(row["q2"], 0.0)
            self.assertEqual(row["q_demand"], 1.2)
            self.assertEqual(row["q_out"], 1.2)
            self.assertEqual(row["q_delivered"], row["q_out"])
        self.assertTrue(record["simulation"]["safe"])
        self.assertTrue(record["simulation"]["continuous_service"])
        self.assertTrue(record["simulation"]["transfer_by_state_dependent_deadline"])

    def test_margin_boundary_traces_are_not_safe(self) -> None:
        report = evaluate_state_dependent_workflows()
        records = report["flowing_startup_contexts"]
        self.assertFalse(records["near_t1_overflow"]["simulation"]["safe"])
        self.assertFalse(records["near_t2_depletion"]["simulation"]["safe"])
        self.assertTrue(records["inadequate_backup_capacity"]["simulation"]["safe"])
        self.assertFalse(records["inadequate_backup_capacity"]["simulation"]["continuous_service"])
        self.assertTrue(records["startup_after_transfer_deadline"]["simulation"]["safe"])
        self.assertFalse(
            records["startup_after_transfer_deadline"]["simulation"]["transfer_by_state_dependent_deadline"]
        )

    def test_controlled_hold_and_flowing_startup_are_distinct_traces(self) -> None:
        report = evaluate_state_dependent_workflows()
        hold = report["controlled_hold_baseline"]["simulation"]["startup_trace"]
        flowing = report["flowing_startup_contexts"]["safe_recoverable"]["simulation"]["startup_trace"]
        self.assertEqual([row["q_in"] for row in hold], [0.0, 0.0])
        self.assertEqual([row["q_out"] for row in hold], [0.0, 0.0])
        self.assertEqual([row["q_in"] for row in flowing], [1.0, 1.0])
        self.assertEqual([row["q_out"] for row in flowing], [1.2, 1.2])


class StateDependentFormalAndCertificateTests(unittest.TestCase):
    def test_static_artifact_matches_state_dependent_renderer(self) -> None:
        expected = render_state_dependent_recovery_envelope().envelope_text
        static = (Path(__file__).resolve().parents[1] / "state_dependent_recovery_takeover.envelope").read_text()
        self.assertEqual(static, expected)

    def test_state_dependent_game_has_nonzero_flow_margins_and_mandatory_operation(self) -> None:
        text = render_state_dependent_recovery_envelope().envelope_text
        self.assertIn("x1 + startupInflow * StartupDelay <= H1", text)
        self.assertIn("x2 - startupWithdrawal * StartupDelay >= L2", text)
        self.assertIn("x1' = qin - q1 - q2", text)
        self.assertIn("x2' = q1 + q2 - qout", text)
        self.assertIn("qout := demand;", text)
        self.assertIn("qdelivered := qout;", text)
        self.assertIn("? startupClock >= StartupDelay;", text)
        self.assertIn("? operationClock >= T;", text)
        self.assertIn("operation_ode:", text)
        self.assertNotIn("}*", text)

    def test_concrete_envelope_binds_the_safe_runtime_state(self) -> None:
        context = state_dependent_evaluation_contexts()["safe_recoverable"]
        text = render_state_dependent_context_envelope(context).envelope_text
        self.assertIn("x1 = 7", text)
        self.assertIn("x2 = 6", text)
        self.assertIn("startupInflow = 1", text)
        self.assertIn("startupWithdrawal = 1.2", text)
        self.assertIn("TransferDeadline = 1.5", text)

    def test_only_the_derived_interior_region_is_authorized(self) -> None:
        contexts = state_dependent_evaluation_contexts()
        self.assertEqual(
            check_state_dependent_recovery(contexts["safe_recoverable"]).status,
            CertificateStatus.COVERED_BY_CERTIFICATE,
        )
        for name in (
            "near_t1_overflow",
            "near_t2_depletion",
            "inadequate_backup_capacity",
            "startup_after_transfer_deadline",
        ):
            self.assertEqual(
                check_state_dependent_recovery(contexts[name]).status,
                CertificateStatus.NOT_COVERED_BY_CERTIFICATE,
                name,
            )

    def test_unaligned_startup_delay_is_not_authorized_for_the_discrete_trace(self) -> None:
        context = state_dependent_evaluation_contexts()["safe_recoverable"]
        unaligned = replace(
            context,
            plant=replace(context.plant, backup_startup_delay=1.1),
            recovery_timing=replace(context.recovery_timing, backup_startup_delay=1.1),
        )
        self.assertEqual(
            check_state_dependent_recovery(unaligned).status,
            CertificateStatus.NOT_COVERED_BY_CERTIFICATE,
        )

    def test_old_and_new_certificates_do_not_authorize_each_others_policy(self) -> None:
        new_context = state_dependent_evaluation_contexts()["safe_recoverable"]
        old_context = controlled_hold_baseline_context()
        self.assertEqual(
            check_certified_recovery(new_context).status,
            CertificateStatus.INCOMPATIBLE_CONTEXT,
        )
        self.assertEqual(
            check_state_dependent_recovery(old_context).status,
            CertificateStatus.INCOMPATIBLE_CONTEXT,
        )

    def test_alternate_or_changed_manifest_cannot_authorize_context(self) -> None:
        context = state_dependent_evaluation_contexts()["safe_recoverable"]
        with tempfile.TemporaryDirectory() as directory:
            alternate = Path(directory) / "manifest.json"
            alternate.write_text('{"verification_status": "VERIFIED"}')
            self.assertEqual(
                check_state_dependent_recovery(context, manifest_path=alternate).status,
                CertificateStatus.UNTRUSTED_CERTIFICATE,
            )
        with patch(
            "recovery_experiment.state_dependent_certificate._sha256_bytes",
            side_effect=[TRUSTED_MANIFEST_SHA256, "changed-artifact-digest"],
        ):
            self.assertEqual(
                check_state_dependent_recovery(context).status,
                CertificateStatus.UNTRUSTED_CERTIFICATE,
            )

    def test_reviewed_nonverified_status_is_distinguished(self) -> None:
        context = state_dependent_evaluation_contexts()["safe_recoverable"]
        with patch(
            "recovery_experiment.state_dependent_certificate._load_prevalidated_manifest",
            return_value={
                "certificate_id": "two-tank-flowing-takeover-state-dependent-v1",
                "verification_status": "UNVERIFIED",
            },
        ):
            self.assertEqual(
                check_state_dependent_recovery(context).status,
                CertificateStatus.UNVERIFIED,
            )

    def test_runtime_check_does_not_invoke_cleo(self) -> None:
        context = state_dependent_evaluation_contexts()["safe_recoverable"]
        with patch(
            "recovery_experiment.verify_state_dependent_recovery.verify_state_dependent_theorem",
            side_effect=AssertionError("runtime checker must not invoke CLEO"),
        ):
            self.assertEqual(
                check_state_dependent_recovery(context).status,
                CertificateStatus.COVERED_BY_CERTIFICATE,
            )

    def test_evaluation_is_reproducible_except_for_latency(self) -> None:
        one = evaluate_state_dependent_workflows()
        two = evaluate_state_dependent_workflows()
        self.assertEqual(one["comparison_note"], two["comparison_note"])
        for name, first in one["flowing_startup_contexts"].items():
            second = two["flowing_startup_contexts"][name]
            self.assertEqual(first["context"], second["context"])
            self.assertEqual(first["certificate"]["status"], second["certificate"]["status"])
            self.assertEqual(first["certificate"]["reasons"], second["certificate"]["reasons"])
            self.assertEqual(first["simulation"], second["simulation"])
            self.assertEqual(first["cost"], second["cost"])


class OptionalStateDependentIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("RUN_CLEO_REGRESSION") == "1", "set RUN_CLEO_REGRESSION=1")
    def test_symbolic_state_dependent_theorem_is_verified(self) -> None:
        from recovery_experiment.formal import FormalStatus
        from recovery_experiment.verify_state_dependent_recovery import verify_state_dependent_theorem

        result = verify_state_dependent_theorem()
        self.assertEqual(result.status, FormalStatus.VERIFIED, result.reason)
        self.assertTrue(all(milestone["passed"] for milestone in result.milestones.values()))

    @unittest.skipUnless(os.environ.get("RUN_CLEO_REGRESSION") == "1", "set RUN_CLEO_REGRESSION=1")
    def test_safe_interior_context_is_independently_verified(self) -> None:
        from recovery_experiment.formal import FormalStatus
        from recovery_experiment.verify_state_dependent_context import verify_state_dependent_context

        context = state_dependent_evaluation_contexts()["safe_recoverable"]
        self.assertEqual(
            check_state_dependent_recovery(context).status,
            CertificateStatus.COVERED_BY_CERTIFICATE,
        )
        self.assertEqual(verify_state_dependent_context(context).status, FormalStatus.VERIFIED)
