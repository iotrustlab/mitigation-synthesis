"""Reviewed runtime applicability for the generated one-control-period theorem.

This checker validates a locally reviewed provenance manifest and a runtime
context. It never runs CLEO, simulates a recovery, or commands an actuator.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path

from .certificate import CertificateCoverageResult, CertificateStatus
from .context import ContextValidationError, RecoveryContext
from .intermediate_delay_formal import (
    INTERMEDIATE_DELAY_PLANT_MODEL_ID,
    INTERMEDIATE_DELAY_POLICY_ID,
    render_intermediate_delay_recovery_envelope,
)
from .intermediate_delay_proof_profile import INTERMEDIATE_DELAY_PROOF_PROFILE_ID
from .model import AttackerAction
from .recovery_model_builder import INTERMEDIATE_DELAY_MODEL_ID


CERTIFICATE_ID = "one-control-period-flowing-takeover-reviewed-v1"
_ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST_PATH = _ROOT / "intermediate_delay_certificate_manifest.json"
# This checked-in digest is a local reviewed trust anchor, not a signature.
TRUSTED_MANIFEST_SHA256 = "707176f28a875a55d6afcf0428582f172c6f3354f64b9fa422cc1da1d1051f21"


class CertificateManifestError(ValueError):
    """Raised when local reviewed provenance cannot be validated."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_prevalidated_manifest(manifest_path: Path | None = None) -> dict[str, object]:
    """Load the one checked-in reviewed 1T manifest and all bound artifacts."""

    path = (manifest_path or DEFAULT_MANIFEST_PATH).resolve()
    if path != DEFAULT_MANIFEST_PATH.resolve():
        raise CertificateManifestError("only the repository's prevalidated manifest is authorizing")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise CertificateManifestError(f"certificate manifest is unavailable: {exc}") from exc
    if not TRUSTED_MANIFEST_SHA256 or TRUSTED_MANIFEST_SHA256.startswith("TO_BE_"):
        raise CertificateManifestError("reviewed intermediate-delay manifest digest has not been configured")
    if _sha256_bytes(payload) != TRUSTED_MANIFEST_SHA256:
        raise CertificateManifestError("certificate manifest digest does not match the reviewed trust anchor")
    try:
        manifest = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise CertificateManifestError(f"certificate manifest is invalid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise CertificateManifestError("certificate manifest must be a JSON object")
    required = {
        "certificate_id": CERTIFICATE_ID,
        "formal_model_id": INTERMEDIATE_DELAY_MODEL_ID,
        "plant_model_id": INTERMEDIATE_DELAY_PLANT_MODEL_ID,
        "recovery_policy_id": INTERMEDIATE_DELAY_POLICY_ID,
        "proof_profile_id": INTERMEDIATE_DELAY_PROOF_PROFILE_ID,
        "verification_status": "VERIFIED",
        "review_state": "CERTIFICATE_ISSUED",
    }
    for key, value in required.items():
        if manifest.get(key) != value:
            raise CertificateManifestError(f"certificate manifest has unexpected {key}")
    schedule = manifest.get("schedule")
    if schedule != {"isolation_periods": 1, "startup_periods": 3}:
        raise CertificateManifestError("certificate manifest is not bound to the exact 1T/3T timing shape")
    if manifest.get("verification_artifact_path") != "proof_records/intermediate_delay_1t/intermediate_delay_verification.json":
        raise CertificateManifestError("certificate manifest is not bound to the reviewed 1T proof record")
    if manifest.get("proof_result") != {"all_obligations_passed": True, "obligation_count": 4}:
        raise CertificateManifestError("certificate manifest does not record the complete successful 1T proof result")
    if manifest.get("verified_obligations") != {
        "bb": "isolation_pending_phase_1",
        "bi": "backup_pending_phase",
        "bv": "operation_phase",
        "a": "top_level_arithmetic",
    }:
        raise CertificateManifestError("certificate manifest does not bind the expected 1T proof obligations")
    artifacts = manifest.get("proof_artifacts")
    if not isinstance(artifacts, dict):
        raise CertificateManifestError("certificate manifest has no bound proof artifacts")
    if manifest.get("renderer_sha256") != artifacts.get("recovery_model_builder.py"):
        raise CertificateManifestError("certificate manifest renderer digest is not bound to the builder artifact")
    for filename, expected_digest in artifacts.items():
        if not isinstance(filename, str) or not isinstance(expected_digest, str):
            raise CertificateManifestError("certificate artifact binding is malformed")
        try:
            actual_digest = _sha256_bytes((_ROOT / filename).read_bytes())
        except OSError as exc:
            raise CertificateManifestError(f"bound proof artifact is unavailable: {filename}") from exc
        if actual_digest != expected_digest:
            raise CertificateManifestError(f"bound proof artifact digest changed: {filename}")
    generated_digest = manifest.get("generated_envelope_sha256")
    if not isinstance(generated_digest, str):
        raise CertificateManifestError("certificate manifest has no generated-envelope digest")
    actual_generated_digest = _sha256_bytes(
        render_intermediate_delay_recovery_envelope().envelope_text.encode()
    )
    if actual_generated_digest != generated_digest:
        raise CertificateManifestError("deterministically regenerated 1T envelope differs from the reviewed artifact")
    return manifest


def reviewed_intermediate_artifact_available() -> bool:
    """Check local provenance only; false never means that recovery is impossible."""

    try:
        _load_prevalidated_manifest()
    except CertificateManifestError:
        return False
    return True


def _same(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=1e-12)


def _result(
    status: CertificateStatus,
    reasons: list[str] | tuple[str, ...],
    started: float,
    certificate_id: str | None,
) -> CertificateCoverageResult:
    return CertificateCoverageResult(status, tuple(reasons), (time.perf_counter() - started) * 1_000, certificate_id)


def check_intermediate_delay_recovery(
    context: RecoveryContext,
    *,
    attacker_schedule: tuple[AttackerAction, ...] | None = None,
    manifest_path: Path | None = None,
) -> CertificateCoverageResult:
    """Authorize only a reviewed 1T/3T theorem context and action schedule."""

    started = time.perf_counter()
    try:
        context.validate()
    except (ContextValidationError, ValueError) as exc:
        return _result(CertificateStatus.INVALID_CONTEXT, [str(exc)], started, None)
    try:
        manifest = _load_prevalidated_manifest(manifest_path)
    except CertificateManifestError as exc:
        return _result(CertificateStatus.UNTRUSTED_CERTIFICATE, [str(exc)], started, None)

    certificate_id = str(manifest["certificate_id"])
    if context.plant_model_id != INTERMEDIATE_DELAY_PLANT_MODEL_ID:
        return _result(CertificateStatus.INCOMPATIBLE_CONTEXT, ["context plant model does not match the reviewed 1T model"], started, certificate_id)
    if context.recovery_policy_id != INTERMEDIATE_DELAY_POLICY_ID:
        return _result(CertificateStatus.INCOMPATIBLE_CONTEXT, ["context recovery policy does not match the reviewed 1T policy"], started, certificate_id)

    plant, assurance, state = context.plant, context.takeover_assurance, context.current_state
    reasons: list[str] = []
    if not context.resource_availability.trusted_isolation_available:
        reasons.append("certificate requires incident-trusted independent primary isolation")
    if not context.resource_availability.trusted_backup_available:
        reasons.append("certificate requires an incident-trusted P2 backup control path")
    allowed = frozenset({AttackerAction.FORCE_PRIMARY_OFF, AttackerAction.FORCE_PRIMARY_ON})
    if context.attacker_capabilities != allowed:
        reasons.append("certificate requires both modeled binary P1 command capabilities")
    if attacker_schedule is not None and (
        len(attacker_schedule) != 1 or any(action not in allowed for action in attacker_schedule)
    ):
        reasons.append("1T theorem traces may supply exactly one pre-isolation binary P1 command")
    if "primary_isolator" not in context.trusted_actuators or context.available_recovery_resources.get("primary_isolation") is not True:
        reasons.append("certificate requires an independent trusted physical primary isolator")
    if "P2_command" not in context.trusted_actuators:
        reasons.append("certificate requires an independent trusted P2 command path")
    if context.available_recovery_resources.get("backup_capacity") != plant.backup_capacity:
        reasons.append("declared backup capacity does not match the plant configuration")
    if plant.low_t1 < 0 or plant.low_t2 < 0:
        reasons.append("certificate requires nonnegative tank lower bounds")
    if not (plant.low_t1 <= state.x1 <= plant.high_t1 and plant.low_t2 <= state.x2 <= plant.high_t2):
        reasons.append("current tank state is outside the certified closed safety region")
    if plant.control_period <= 0:
        reasons.append("control period must be positive")
    if not _same(plant.isolation_delay, plant.control_period):
        reasons.append("isolation delay must equal exactly one control period")
    if not _same(plant.backup_startup_delay, 3 * plant.control_period):
        reasons.append("backup startup delay must equal exactly three control periods")
    if plant.backup_startup_delay > plant.transfer_recovery_deadline:
        reasons.append("backup startup delay exceeds the certified transfer recovery deadline")
    if plant.horizon <= plant.backup_startup_delay:
        reasons.append("finite assurance horizon must leave a positive post-takeover operation duration")
    if plant.startup_inflow_rate < 0:
        reasons.append("startup inflow must be nonnegative")
    if plant.min_service_flow <= 0 or plant.startup_withdrawal_rate < plant.min_service_flow:
        reasons.append("startup withdrawal does not establish the certified continuous delivered service")
    if plant.primary_capacity < plant.startup_inflow_rate or plant.primary_capacity < plant.startup_withdrawal_rate:
        reasons.append("primary capacity does not cover the 1T theorem startup flow bounds")
    if plant.backup_capacity < plant.min_service_flow:
        reasons.append("backup capacity does not establish the certified post-takeover service")
    if plant.backup_capacity != plant.upstream_nominal or plant.backup_capacity != plant.downstream_demand:
        reasons.append("certificate requires balanced post-takeover inflow, withdrawal, and backup flow")
    if state.x1 + plant.startup_inflow_rate * plant.backup_startup_delay > plant.high_t1:
        reasons.append("upstream full-startup margin can exceed the T1 high safety bound")
    if state.x1 + (plant.startup_inflow_rate - plant.primary_capacity) * plant.isolation_delay < plant.low_t1:
        reasons.append("upstream P1-on delay margin can fall below the T1 low safety bound")
    if state.x2 - plant.startup_withdrawal_rate * plant.backup_startup_delay < plant.low_t2:
        reasons.append("downstream full-startup margin can fall below the T2 low safety bound")
    if state.x2 + (plant.primary_capacity - plant.startup_withdrawal_rate) * plant.isolation_delay > plant.high_t2:
        reasons.append("downstream P1-on delay margin can exceed the T2 high safety bound")
    if assurance.intervention_budget < assurance.isolation_cost + assurance.backup_activation_cost:
        reasons.append("intervention budget does not cover trusted isolation plus backup activation")
    if reasons:
        return _result(CertificateStatus.NOT_COVERED_BY_CERTIFICATE, reasons, started, certificate_id)
    return _result(
        CertificateStatus.COVERED_BY_CERTIFICATE,
        (
            "validated context satisfies every assumption of the reviewed generated 1T theorem",
            "the theorem covers both binary P1 choices over its one pre-isolation period",
        ),
        started,
        certificate_id,
    )
