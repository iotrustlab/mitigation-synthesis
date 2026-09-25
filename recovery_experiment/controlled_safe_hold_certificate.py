"""Runtime authorization for the separately reviewed controlled-safe-hold theorem.

This checker does not prove a theorem, invoke CLEO, or make a deployment claim.
It authorizes only contexts that match the distinct safe-hold proof, manifest,
and incident-specific trusted resource contract.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path

from .certificate import CertificateCoverageResult, CertificateManifestError, CertificateStatus
from .context import ContextValidationError, RecoveryContext
from .controlled_safe_hold_formal import (
    CONTROLLED_SAFE_HOLD_MODEL_ID,
    CONTROLLED_SAFE_HOLD_PLANT_MODEL_ID,
    CONTROLLED_SAFE_HOLD_POLICY_ID,
    CONTROLLED_SAFE_HOLD_PROOF_PROFILE_ID,
    render_controlled_safe_hold_envelope,
)
from .model import AttackerAction


CERTIFICATE_ID = "two-tank-controlled-safe-hold-immediate-isolation-v1"
_ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST_PATH = _ROOT / "controlled_safe_hold_certificate_manifest.json"
# The local reviewed-manifest digest is a trust anchor, not a signature or deployment authority.
TRUSTED_MANIFEST_SHA256 = "0fd6d74b533c4e81b646170f5898a5a554acd8de72895953a4bc55099b956d5f"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_prevalidated_manifest(manifest_path: Path | None = None) -> dict[str, object]:
    """Load only the anchored manifest and check its exact proof-artifact bindings."""

    path = (manifest_path or DEFAULT_MANIFEST_PATH).resolve()
    if path != DEFAULT_MANIFEST_PATH.resolve():
        raise CertificateManifestError("only the repository's prevalidated manifest is authorizing")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise CertificateManifestError(f"certificate manifest is unavailable: {exc}") from exc
    if not TRUSTED_MANIFEST_SHA256:
        raise CertificateManifestError("reviewed controlled-safe-hold manifest digest has not been configured")
    if _sha256_bytes(payload) != TRUSTED_MANIFEST_SHA256:
        raise CertificateManifestError("certificate manifest digest does not match the reviewed trust anchor")
    try:
        manifest = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise CertificateManifestError(f"certificate manifest is invalid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise CertificateManifestError("certificate manifest must be a JSON object")
    expected = {
        "certificate_id": CERTIFICATE_ID,
        "formal_model_id": CONTROLLED_SAFE_HOLD_MODEL_ID,
        "recovery_policy_id": CONTROLLED_SAFE_HOLD_POLICY_ID,
        "proof_profile_id": CONTROLLED_SAFE_HOLD_PROOF_PROFILE_ID,
        "verification_status": "VERIFIED",
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise CertificateManifestError(f"certificate manifest {key} is not bound to the controlled-safe-hold theorem")
    artifacts = manifest.get("proof_artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise CertificateManifestError("certificate has no bound proof artifacts")
    for filename, expected_digest in artifacts.items():
        if not isinstance(filename, str) or not isinstance(expected_digest, str):
            raise CertificateManifestError("certificate artifact binding is malformed")
        artifact = _ROOT / filename
        try:
            actual_digest = _sha256_bytes(artifact.read_bytes())
        except OSError as exc:
            raise CertificateManifestError(f"bound proof artifact is unavailable: {filename}") from exc
        if actual_digest != expected_digest:
            raise CertificateManifestError(f"bound proof artifact digest changed: {filename}")
    expected_envelope_digest = artifacts.get(
        "proof_records/controlled_safe_hold/controlled_safe_hold.generated.envelope"
    )
    if expected_envelope_digest != _sha256_bytes(render_controlled_safe_hold_envelope().envelope_text.encode()):
        raise CertificateManifestError("generated safe-hold theorem no longer matches the reviewed proof envelope")
    try:
        verification = json.loads(
            (_ROOT / "proof_records/controlled_safe_hold/controlled_safe_hold_verification.json").read_text()
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise CertificateManifestError("controlled-safe-hold verification record is unavailable or invalid") from exc
    if not (
        verification.get("status") == "VERIFIED"
        and verification.get("formal_model_id") == CONTROLLED_SAFE_HOLD_MODEL_ID
        and verification.get("proof_profile_id") == CONTROLLED_SAFE_HOLD_PROOF_PROFILE_ID
        and isinstance(verification.get("obligations"), list)
        and verification["obligations"]
        and all(obligation.get("passed") is True for obligation in verification["obligations"])
    ):
        raise CertificateManifestError("controlled-safe-hold proof record does not establish a verified theorem")
    return manifest


def _result(
    status: CertificateStatus,
    reasons: list[str] | tuple[str, ...],
    started: float,
    certificate_id: str | None,
) -> CertificateCoverageResult:
    return CertificateCoverageResult(status, tuple(reasons), (time.perf_counter() - started) * 1_000, certificate_id)


def reviewed_controlled_safe_hold_artifact_available() -> bool:
    """Report local reviewed provenance availability without authorizing an incident."""

    try:
        _load_prevalidated_manifest()
    except CertificateManifestError:
        return False
    return True


def check_controlled_safe_hold_recovery(
    context: RecoveryContext,
    *,
    attacker_schedule: tuple[AttackerAction, ...] | None = None,
    manifest_path: Path | None = None,
) -> CertificateCoverageResult:
    """Authorize a finite safety hold only when independent authority is explicit.

    The theorem permits no delayed isolation. A supplied schedule can contain one
    binary P1 action immediately before isolation; omitted schedules are sound
    because the symbolic game quantifies both choices.
    """

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
    if context.plant_model_id != CONTROLLED_SAFE_HOLD_PLANT_MODEL_ID:
        return _result(CertificateStatus.INCOMPATIBLE_CONTEXT, ["context plant model does not match the controlled-safe-hold theorem"], started, certificate_id)
    if context.recovery_policy_id != CONTROLLED_SAFE_HOLD_POLICY_ID:
        return _result(CertificateStatus.INCOMPATIBLE_CONTEXT, ["context recovery policy does not match the controlled-safe-hold policy"], started, certificate_id)

    plant, state, assurance = context.plant, context.current_state, context.takeover_assurance
    resources = context.resource_availability
    reasons: list[str] = []
    allowed_actions = frozenset({AttackerAction.FORCE_PRIMARY_OFF, AttackerAction.FORCE_PRIMARY_ON})
    if context.attacker_capabilities != allowed_actions:
        reasons.append("certificate requires both modeled binary P1 command capabilities")
    if attacker_schedule is not None and (
        len(attacker_schedule) != 1 or any(action not in allowed_actions for action in attacker_schedule)
    ):
        reasons.append("safe-hold theorem traces may supply exactly one pre-isolation P1 command")
    if not resources.trusted_isolation_available or "primary_isolator" not in context.trusted_actuators:
        reasons.append("certificate requires an incident-trusted independent primary isolation control path")
    if not resources.trusted_inflow_control_available or "upstream_gate" not in context.trusted_actuators:
        reasons.append("certificate requires an incident-trusted upstream inflow closure path")
    if not resources.trusted_demand_control_available or "demand_gate" not in context.trusted_actuators:
        reasons.append("certificate requires an incident-trusted downstream delivery-curtailment path")
    if context.available_recovery_resources.get("primary_isolation") is not True:
        reasons.append("the physical primary isolator is not explicitly present")
    if not math.isclose(plant.isolation_delay, 0.0, rel_tol=0.0, abs_tol=1e-12):
        reasons.append("certificate supports immediate physical isolation only")
    if plant.horizon <= 0:
        reasons.append("certificate requires a positive finite safe-hold horizon")
    if plant.downstream_demand <= 0:
        reasons.append("certificate requires positive external demand to distinguish curtailment from absent demand")
    if plant.low_t1 < 0 or plant.low_t2 < 0:
        reasons.append("certificate requires nonnegative tank lower bounds")
    if not (plant.low_t1 <= state.x1 <= plant.high_t1 and plant.low_t2 <= state.x2 <= plant.high_t2):
        reasons.append("current tank state is outside the certified closed safety region")
    if plant.primary_capacity < 0:
        reasons.append("certificate requires nonnegative primary capacity")
    if assurance.intervention_budget < assurance.isolation_cost + assurance.hold_control_cost:
        reasons.append("intervention budget does not cover trusted isolation plus safe-hold controls")
    if reasons:
        return _result(CertificateStatus.NOT_COVERED_BY_CERTIFICATE, reasons, started, certificate_id)
    return _result(
        CertificateStatus.COVERED_BY_CERTIFICATE,
        (
            "validated context satisfies the reviewed immediate-isolation controlled-safe-hold theorem",
            "P1 remains attacker-commandable before isolation, but independent physical isolation and both hold gates are explicit",
            "external demand remains positive while the certified hold intentionally delivers zero service",
        ),
        started,
        certificate_id,
    )
