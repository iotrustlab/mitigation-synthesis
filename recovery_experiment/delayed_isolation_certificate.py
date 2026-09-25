"""Offline-prepared certificate applicability for delayed P1 isolation.

This module checks the assumptions of the separately verified delayed-isolation
theorem.  It is deliberately a local, deterministic applicability check: it
does not invoke CLEO, simulate a trace, or command an actuator.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path

from .certificate import CertificateCoverageResult, CertificateStatus
from .context import ContextValidationError, RecoveryContext
from .delayed_isolation_formal import (
    DELAYED_ISOLATION_MODEL_ID,
    DELAYED_ISOLATION_PLANT_MODEL_ID,
    DELAYED_ISOLATION_POLICY_ID,
)
from .delayed_isolation_proof_profile import DELAYED_ISOLATION_PROOF_PROFILE_ID
from .model import AttackerAction


CERTIFICATE_ID = "two-tank-flowing-takeover-delayed-isolation-v1"
_ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST_PATH = _ROOT / "delayed_isolation_certificate_manifest.json"
# This reviewed digest is the local trust anchor, not a self-authenticating signature.
TRUSTED_MANIFEST_SHA256 = "0658f30df2c0067e9bc1e12d6a37fb1bdf36a8e7fac71f2c6a04d893b40154c5"


class CertificateManifestError(ValueError):
    """Raised when the local provenance binding cannot be trusted."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_prevalidated_manifest(manifest_path: Path | None = None) -> dict[str, object]:
    """Load only the canonical manifest and verify every bound proof artifact."""

    path = (manifest_path or DEFAULT_MANIFEST_PATH).resolve()
    if path != DEFAULT_MANIFEST_PATH.resolve():
        raise CertificateManifestError("only the repository's prevalidated manifest is authorizing")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise CertificateManifestError(f"certificate manifest is unavailable: {exc}") from exc
    if not TRUSTED_MANIFEST_SHA256:
        raise CertificateManifestError("reviewed delayed-isolation manifest digest has not been configured")
    if _sha256_bytes(payload) != TRUSTED_MANIFEST_SHA256:
        raise CertificateManifestError("certificate manifest digest does not match the reviewed trust anchor")
    try:
        manifest = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise CertificateManifestError(f"certificate manifest is invalid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise CertificateManifestError("certificate manifest must be a JSON object")
    if manifest.get("certificate_id") != CERTIFICATE_ID:
        raise CertificateManifestError("certificate identifier is not the reviewed delayed-isolation certificate")
    if manifest.get("formal_model_id") != DELAYED_ISOLATION_MODEL_ID:
        raise CertificateManifestError("certificate is bound to a different formal model")
    if manifest.get("proof_profile_id") != DELAYED_ISOLATION_PROOF_PROFILE_ID:
        raise CertificateManifestError("certificate is bound to a different proof profile")
    if manifest.get("verification_status") not in {"VERIFIED", "UNVERIFIED"}:
        raise CertificateManifestError("certificate has an invalid verification status")
    artifacts = manifest.get("proof_artifacts")
    if not isinstance(artifacts, dict):
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
    return manifest


def _result(
    status: CertificateStatus,
    reasons: list[str] | tuple[str, ...],
    started: float,
    certificate_id: str | None,
) -> CertificateCoverageResult:
    return CertificateCoverageResult(
        status,
        tuple(reasons),
        (time.perf_counter() - started) * 1_000,
        certificate_id,
    )


def _same(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=1e-12)


def _schedule_reasons(
    attacker_schedule: tuple[AttackerAction, ...] | None,
) -> list[str]:
    """Validate an optional trace schedule against the theorem's two choices.

    The symbolic game universally quantifies both P1 choices, so a schedule is
    not required to authorize the theorem.  A supplied schedule is accepted
    only when it names exactly those two pre-isolation binary commands.
    """

    if attacker_schedule is None:
        return []
    allowed = {AttackerAction.FORCE_PRIMARY_OFF, AttackerAction.FORCE_PRIMARY_ON}
    if len(attacker_schedule) != 2:
        return ["delayed theorem traces may supply exactly two pre-isolation P1 commands"]
    if any(action not in allowed for action in attacker_schedule):
        return ["delayed theorem permits only binary P1 off/on commands before isolation"]
    return []


def check_delayed_isolation_recovery(
    context: RecoveryContext,
    *,
    attacker_schedule: tuple[AttackerAction, ...] | None = None,
    manifest_path: Path | None = None,
) -> CertificateCoverageResult:
    """Authorize exactly the verified delayed-isolation theorem region.

    ``attacker_schedule=None`` means no particular trace is assumed.  This is
    sound because the theorem covers every binary choice pair at the two
    pre-isolation control boundaries.  A positive result is not a deployment
    claim: it relies on the context's declared independent physical isolator.
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
    if manifest["verification_status"] != "VERIFIED":
        return _result(
            CertificateStatus.UNVERIFIED,
            ["reviewed manifest does not record a verified delayed-isolation theorem"],
            started,
            certificate_id,
        )
    if context.plant_model_id != DELAYED_ISOLATION_PLANT_MODEL_ID:
        return _result(
            CertificateStatus.INCOMPATIBLE_CONTEXT,
            ["context plant model does not match the proved delayed-isolation model"],
            started,
            certificate_id,
        )
    if context.recovery_policy_id != DELAYED_ISOLATION_POLICY_ID:
        return _result(
            CertificateStatus.INCOMPATIBLE_CONTEXT,
            ["context recovery policy does not match the proved delayed-isolation takeover policy"],
            started,
            certificate_id,
        )

    plant, assurance, state = context.plant, context.takeover_assurance, context.current_state
    reasons = _schedule_reasons(attacker_schedule)
    if not context.resource_availability.trusted_isolation_available:
        reasons.append("certificate requires incident-trusted independent primary isolation")
    if not context.resource_availability.trusted_backup_available:
        reasons.append("certificate requires an incident-trusted P2 backup control path")
    expected_actions = frozenset({AttackerAction.FORCE_PRIMARY_OFF, AttackerAction.FORCE_PRIMARY_ON})
    if context.attacker_capabilities != expected_actions:
        reasons.append("certificate requires both modeled binary P1 command capabilities")
    if "primary_isolator" not in context.trusted_actuators:
        reasons.append("certificate requires an independent trusted primary isolator")
    if "P2_command" not in context.trusted_actuators:
        reasons.append("certificate requires an independent trusted P2 command path")
    if context.available_recovery_resources.get("primary_isolation") is not True:
        reasons.append("trusted physical primary isolation is not explicitly available")
    if context.available_recovery_resources.get("backup_capacity") != plant.backup_capacity:
        reasons.append("declared backup capacity does not match the plant configuration")
    if plant.low_t1 < 0 or plant.low_t2 < 0:
        reasons.append("certificate requires nonnegative tank lower bounds")
    if not (
        plant.low_t1 <= state.x1 <= plant.high_t1
        and plant.low_t2 <= state.x2 <= plant.high_t2
    ):
        reasons.append("current tank state is outside the certified closed safety region")
    if plant.control_period <= 0:
        reasons.append("control period must be positive")
    if not _same(plant.isolation_delay, 2 * plant.control_period):
        reasons.append("isolation delay must equal exactly two control periods")
    if not _same(plant.backup_startup_delay, 3 * plant.control_period):
        reasons.append("backup startup delay must equal exactly three control periods")
    if plant.isolation_delay <= 0 or plant.isolation_delay > plant.backup_startup_delay:
        reasons.append("certificate requires positive isolation delay no later than backup availability")
    if plant.backup_startup_delay > plant.transfer_recovery_deadline:
        reasons.append("backup startup delay exceeds the certified transfer recovery deadline")
    if plant.horizon <= plant.backup_startup_delay:
        reasons.append("finite assurance horizon must leave a positive post-takeover operation duration")
    if plant.startup_inflow_rate < 0:
        reasons.append("startup inflow must be nonnegative")
    if plant.min_service_flow <= 0 or plant.startup_withdrawal_rate < plant.min_service_flow:
        reasons.append("startup withdrawal does not establish the certified continuous delivered service")
    if plant.primary_capacity < plant.startup_inflow_rate or plant.primary_capacity < plant.startup_withdrawal_rate:
        reasons.append("primary capacity does not cover the delayed theorem's startup flow bounds")
    if plant.backup_capacity < plant.min_service_flow:
        reasons.append("backup capacity does not establish the certified post-takeover service")
    if (
        plant.backup_capacity != plant.upstream_nominal
        or plant.backup_capacity != plant.downstream_demand
    ):
        reasons.append("certificate requires balanced post-takeover inflow, withdrawal, and backup flow")
    if state.x1 + plant.startup_inflow_rate * plant.backup_startup_delay > plant.high_t1:
        reasons.append("upstream full-startup margin can exceed the T1 high safety bound")
    if (
        state.x1 + (plant.startup_inflow_rate - plant.primary_capacity) * plant.isolation_delay
        < plant.low_t1
    ):
        reasons.append("upstream P1-on delay margin can fall below the T1 low safety bound")
    if state.x2 - plant.startup_withdrawal_rate * plant.backup_startup_delay < plant.low_t2:
        reasons.append("downstream full-startup margin can fall below the T2 low safety bound")
    if (
        state.x2 + (plant.primary_capacity - plant.startup_withdrawal_rate) * plant.isolation_delay
        > plant.high_t2
    ):
        reasons.append("downstream P1-on delay margin can exceed the T2 high safety bound")
    if assurance.intervention_budget < assurance.isolation_cost + assurance.backup_activation_cost:
        reasons.append("intervention budget does not cover trusted isolation plus backup activation")
    if reasons:
        return _result(CertificateStatus.NOT_COVERED_BY_CERTIFICATE, reasons, started, certificate_id)
    return _result(
        CertificateStatus.COVERED_BY_CERTIFICATE,
        [
            "validated context satisfies every assumption of the reviewed delayed-isolation theorem",
            "the theorem covers all binary P1 command pairs over the two pre-isolation periods",
        ],
        started,
        certificate_id,
    )
