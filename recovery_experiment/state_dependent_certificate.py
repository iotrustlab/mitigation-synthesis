"""Runtime authorization for the reviewed state-dependent recovery theorem.

This checker performs only deterministic context and provenance checks.  CLEO
proof is an offline preparation step recorded in the reviewed manifest, never a
runtime action.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path

from .certificate import CertificateCoverageResult, CertificateManifestError, CertificateStatus
from .context import ContextValidationError, RecoveryContext
from .state_dependent_formal import (
    STATE_DEPENDENT_MODEL_ID,
    STATE_DEPENDENT_PLANT_MODEL_ID,
    STATE_DEPENDENT_POLICY_ID,
)


CERTIFICATE_ID = "two-tank-flowing-takeover-state-dependent-v1"
_ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST_PATH = _ROOT / "state_dependent_certificate_manifest.json"
# This reviewed digest is the trust anchor, not a claim that JSON is self-authenticating.
TRUSTED_MANIFEST_SHA256 = "fcd6f541068516a62f1b8f77989e0bfc59387492ef1b736533802800394d5d23"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_prevalidated_manifest(manifest_path: Path | None = None) -> dict[str, object]:
    """Load only the reviewed state-dependent manifest and its bound artifacts."""

    path = (manifest_path or DEFAULT_MANIFEST_PATH).resolve()
    if path != DEFAULT_MANIFEST_PATH.resolve():
        raise CertificateManifestError("only the repository's prevalidated manifest is authorizing")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise CertificateManifestError(f"certificate manifest is unavailable: {exc}") from exc
    if _sha256_bytes(payload) != TRUSTED_MANIFEST_SHA256:
        raise CertificateManifestError("certificate manifest digest does not match the reviewed trust anchor")
    try:
        manifest = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise CertificateManifestError(f"certificate manifest is invalid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise CertificateManifestError("certificate manifest must be a JSON object")
    if manifest.get("certificate_id") != CERTIFICATE_ID:
        raise CertificateManifestError("certificate identifier is not the reviewed certificate")
    if manifest.get("formal_model_id") != STATE_DEPENDENT_MODEL_ID:
        raise CertificateManifestError("certificate is bound to a different formal model")
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


def _delay_aligns_to_control_grid(startup_delay: float, control_period: float) -> bool:
    """Keep the discrete trace's startup boundary equal to the exact ODE delay."""

    cycles = startup_delay / control_period
    return math.isclose(cycles, round(cycles), rel_tol=0.0, abs_tol=1e-12)


def check_state_dependent_recovery(
    context: RecoveryContext, *, manifest_path: Path | None = None
) -> CertificateCoverageResult:
    """Authorize exactly the state-dependent flowing-startup theorem region.

    A non-covered context may still be physically safe or recoverable by a
    different policy.  This result expresses only this theorem's scope.
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
            ["reviewed manifest does not record a verified state-dependent theorem"],
            started,
            certificate_id,
        )
    if context.plant_model_id != STATE_DEPENDENT_PLANT_MODEL_ID:
        return _result(
            CertificateStatus.INCOMPATIBLE_CONTEXT,
            ["context plant model does not match the proved state-dependent model"],
            started,
            certificate_id,
        )
    if context.recovery_policy_id != STATE_DEPENDENT_POLICY_ID:
        return _result(
            CertificateStatus.INCOMPATIBLE_CONTEXT,
            ["context recovery policy does not match the proved flowing takeover policy"],
            started,
            certificate_id,
        )

    plant, assurance, state = context.plant, context.takeover_assurance, context.current_state
    reasons: list[str] = []
    if not context.resource_availability.trusted_isolation_available:
        reasons.append("certificate requires incident-trusted independent primary isolation")
    if not context.resource_availability.trusted_backup_available:
        reasons.append("certificate requires an incident-trusted P2 backup control path")
    if "primary_isolator" not in context.trusted_actuators:
        reasons.append("certificate requires an explicit trusted primary-isolator actuator binding")
    if "P2_command" not in context.trusted_actuators:
        reasons.append("certificate requires an explicit trusted P2 command actuator binding")
    if context.available_recovery_resources.get("primary_isolation") is not True:
        reasons.append("certificate requires an explicitly present physical primary isolator")
    if plant.low_t1 < 0 or plant.low_t2 < 0:
        reasons.append("certificate requires nonnegative tank lower bounds")
    if not (
        plant.low_t1 <= state.x1 <= plant.high_t1
        and plant.low_t2 <= state.x2 <= plant.high_t2
    ):
        reasons.append("current tank state is outside the certified closed safety region")
    if plant.startup_inflow_rate < 0:
        reasons.append("startup inflow must be nonnegative")
    if plant.min_service_flow <= 0 or plant.startup_withdrawal_rate < plant.min_service_flow:
        reasons.append("startup withdrawal does not establish the certified continuous delivered service")
    if plant.primary_capacity < 0:
        reasons.append("certificate requires nonnegative primary capacity")
    if plant.backup_capacity < plant.min_service_flow:
        reasons.append("backup capacity does not establish the certified post-takeover service")
    if plant.backup_startup_delay <= 0 or plant.transfer_recovery_deadline <= 0:
        reasons.append("startup duration and transfer recovery deadline must be positive")
    elif plant.backup_startup_delay > plant.transfer_recovery_deadline:
        reasons.append("startup duration exceeds the certified transfer recovery deadline")
    if plant.control_period <= 0:
        reasons.append("mandatory post-takeover operation duration must be positive")
    elif not _delay_aligns_to_control_grid(plant.backup_startup_delay, plant.control_period):
        reasons.append(
            "startup delay must align to the simulator control grid for its trace to match the exact theorem"
        )
    if plant.isolation_delay != 0:
        reasons.append("certificate requires immediate effective trusted isolation")
    if (
        plant.backup_capacity != plant.upstream_nominal
        or plant.backup_capacity != plant.downstream_demand
    ):
        reasons.append("certificate requires balanced post-takeover inflow, withdrawal, and backup flow")
    if state.x1 + plant.startup_inflow_rate * plant.backup_startup_delay > plant.high_t1:
        reasons.append("upstream startup margin can exceed the T1 high safety bound")
    if state.x2 - plant.startup_withdrawal_rate * plant.backup_startup_delay < plant.low_t2:
        reasons.append("downstream startup margin can fall below the T2 low safety bound")
    if assurance.intervention_budget < assurance.isolation_cost + assurance.backup_activation_cost:
        reasons.append("intervention budget does not cover trusted isolation plus backup activation")
    if reasons:
        return _result(CertificateStatus.NOT_COVERED_BY_CERTIFICATE, reasons, started, certificate_id)
    return _result(
        CertificateStatus.COVERED_BY_CERTIFICATE,
        ["validated context satisfies every assumption of the reviewed state-dependent theorem"],
        started,
        certificate_id,
    )
