from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from recovery_experiment.certificate import (
    TRUSTED_MANIFEST_SHA256,
    CertificateStatus,
    check_certified_recovery,
)
from recovery_experiment.certificate_evaluation import (
    certificate_evaluation_contexts,
    evaluate_certificate_workflows,
)
from recovery_experiment.parameterized_formal import render_parameterized_recovery_envelope
from recovery_experiment.scenarios import named_contexts


class ParameterizedCertificateTests(unittest.TestCase):
    def test_static_parameterized_artifact_matches_renderer(self) -> None:
        expected = render_parameterized_recovery_envelope().envelope_text
        static = (Path(__file__).resolve().parents[1] / "parameterized_recovery_takeover.envelope").read_text()
        self.assertEqual(static, expected)

    def test_multiple_safe_initial_states_are_covered(self) -> None:
        contexts = certificate_evaluation_contexts()
        for name in ("certified_interior", "certified_lower_boundary", "certified_upper_boundary"):
            result = check_certified_recovery(contexts[name])
            self.assertEqual(result.status, CertificateStatus.COVERED_BY_CERTIFICATE, name)

    def test_outside_or_unsupported_contexts_are_not_authorized(self) -> None:
        contexts = certificate_evaluation_contexts()
        expected = {
            "outside_safety_region": CertificateStatus.INVALID_CONTEXT,
            "insufficient_backup_capacity": CertificateStatus.NOT_COVERED_BY_CERTIFICATE,
            "startup_after_deadline": CertificateStatus.NOT_COVERED_BY_CERTIFICATE,
            "missing_trusted_isolation": CertificateStatus.INVALID_CONTEXT,
            "unbalanced_flow": CertificateStatus.NOT_COVERED_BY_CERTIFICATE,
            "insufficient_intervention_budget": CertificateStatus.NOT_COVERED_BY_CERTIFICATE,
        }
        for name, status in expected.items():
            self.assertEqual(check_certified_recovery(contexts[name]).status, status, name)

    def test_incompatible_plant_or_policy_is_not_authorized(self) -> None:
        contexts = certificate_evaluation_contexts()
        self.assertEqual(
            check_certified_recovery(contexts["incompatible_plant_model"]).status,
            CertificateStatus.INCOMPATIBLE_CONTEXT,
        )
        self.assertEqual(
            check_certified_recovery(contexts["incompatible_policy"]).status,
            CertificateStatus.INCOMPATIBLE_CONTEXT,
        )

    def test_alternate_or_absent_manifest_cannot_authorize_context(self) -> None:
        context = named_contexts()["baseline_feasible"]
        with tempfile.TemporaryDirectory() as directory:
            alternate = Path(directory) / "manifest.json"
            alternate.write_text('{"verification_status": "VERIFIED"}')
            self.assertEqual(
                check_certified_recovery(context, manifest_path=alternate).status,
                CertificateStatus.UNTRUSTED_CERTIFICATE,
            )
            self.assertEqual(
                check_certified_recovery(context, manifest_path=Path(directory) / "missing.json").status,
                CertificateStatus.UNTRUSTED_CERTIFICATE,
            )

    def test_artifact_digest_mismatch_cannot_authorize_context(self) -> None:
        context = named_contexts()["baseline_feasible"]
        with patch(
            "recovery_experiment.certificate._sha256_bytes",
            side_effect=[TRUSTED_MANIFEST_SHA256, "changed-artifact-digest"],
        ):
            result = check_certified_recovery(context)
        self.assertEqual(result.status, CertificateStatus.UNTRUSTED_CERTIFICATE)

    def test_runtime_check_does_not_run_parameterized_prover(self) -> None:
        context = named_contexts()["baseline_feasible"]
        with patch(
            "recovery_experiment.verify_parameterized_recovery.verify_parameterized_theorem",
            side_effect=AssertionError("runtime checker must not invoke CLEO"),
        ):
            result = check_certified_recovery(context)
        self.assertEqual(result.status, CertificateStatus.COVERED_BY_CERTIFICATE)

    def test_evaluation_is_reproducible_except_for_measured_latency(self) -> None:
        one = evaluate_certificate_workflows()
        two = evaluate_certificate_workflows()
        for name, first in one["contexts"].items():
            second = two["contexts"][name]
            self.assertEqual(first["context_validation"], second["context_validation"])
            self.assertEqual(first["certificate"]["status"], second["certificate"]["status"])
            self.assertEqual(first["certificate"]["reasons"], second["certificate"]["reasons"])
            self.assertEqual(first["simulation"], second["simulation"])


class OptionalParameterizedIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("RUN_CLEO_REGRESSION") == "1", "set RUN_CLEO_REGRESSION=1")
    def test_parameterized_theorem_is_verified(self) -> None:
        from recovery_experiment.formal import FormalStatus
        from recovery_experiment.verify_parameterized_recovery import verify_parameterized_theorem

        result = verify_parameterized_theorem()
        self.assertEqual(result.status, FormalStatus.VERIFIED, result.reason)
        self.assertTrue(all(milestone["passed"] for milestone in result.milestones.values()))

    @unittest.skipUnless(os.environ.get("RUN_CLEO_REGRESSION") == "1", "set RUN_CLEO_REGRESSION=1")
    def test_covered_interior_context_matches_concrete_timed_verification(self) -> None:
        from recovery_experiment.formal import FormalStatus
        from recovery_experiment.verify_timed_recovery import verify_timed_context

        context = certificate_evaluation_contexts()["certified_interior"]
        self.assertEqual(check_certified_recovery(context).status, CertificateStatus.COVERED_BY_CERTIFICATE)
        self.assertEqual(verify_timed_context(context).status, FormalStatus.VERIFIED)
