"""Runtime authorization for the reviewed symbolic trusted-backup certificate.

This module deliberately performs no theorem proving.  It authorizes only
contexts covered by the separately verified symbolic artifact and its trusted
manifest binding.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .context import ContextValidationError, RecoveryContext
from .parameterized_formal import (
    PARAMETERIZED_MODEL_ID,
    PARAMETERIZED_PLANT_MODEL_ID,
    PARAMETERIZED_POLICY_ID,
)


CERTIFICATE_ID = "two-tank-trusted-takeover-parameterized-v1"
_ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST_PATH = _ROOT / "parameterized_certificate_manifest.json"
# This reviewed digest is the trust anchor, not a claim that JSON is self-authenticating.
TRUSTED_MANIFEST_SHA256 = "b5515bde7a60381b8b65aee8bddaa80f781f8490f3cee0b1ff53c0f1ec55b31e"


class CertificateStatus(str, Enum):
    COVERED_BY_CERTIFICATE = "COVERED_BY_CERTIFICATE"
    NOT_COVERED_BY_CERTIFICATE = "NOT_COVERED_BY_CERTIFICATE"
    INVALID_CONTEXT = "INVALID_CONTEXT"
    INCOMPATIBLE_CONTEXT = "INCOMPATIBLE_CONTEXT"
    UNTRUSTED_CERTIFICATE = "UNTRUSTED_CERTIFICATE"
    UNVERIFIED = "UNVERIFIED"


class CertificateManifestError(ValueError):
    """Raised when the reviewed manifest or a bound proof artifact is unavailable."""


@dataclass(frozen=True)
class CertificateCoverageResult:
    status: CertificateStatus
    reasons: tuple[str, ...]
    latency_ms: float
    certificate_id: str | None

    @property
    def covered(self) -> bool:
        return self.status is CertificateStatus.COVERED_BY_CERTIFICATE

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "covered": self.covered,
            "reasons": list(self.reasons),
            "latency_ms": self.latency_ms,
            "certificate_id": self.certificate_id,
        }


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_prevalidated_manifest(manifest_path: Path | None = None) -> dict[str, object]:
    """Load only the repository's reviewed manifest and verify every bound digest."""

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
    if manifest.get("formal_model_id") != PARAMETERIZED_MODEL_ID:
        raise CertificateManifestError("certificate is bound to a different formal model")
    if manifest.get("verification_status") != "VERIFIED":
        raise CertificateManifestError("certificate does not identify a reviewed verified theorem")
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


def _not_covered(reasons: list[str], started: float, certificate_id: str) -> CertificateCoverageResult:
    return CertificateCoverageResult(
        CertificateStatus.NOT_COVERED_BY_CERTIFICATE,
        tuple(reasons),
        (time.perf_counter() - started) * 1_000,
        certificate_id,
    )


def check_certified_recovery(
    context: RecoveryContext, *, manifest_path: Path | None = None
) -> CertificateCoverageResult:
    """Check a runtime context against the offline-proved region without invoking CLEO."""

    started = time.perf_counter()
    try:
        context.validate()
    except (ContextValidationError, ValueError) as exc:
        return CertificateCoverageResult(
            CertificateStatus.INVALID_CONTEXT,
            (str(exc),),
            (time.perf_counter() - started) * 1_000,
            None,
        )

    try:
        manifest = _load_prevalidated_manifest(manifest_path)
    except CertificateManifestError as exc:
        return CertificateCoverageResult(
            CertificateStatus.UNTRUSTED_CERTIFICATE,
            (str(exc),),
            (time.perf_counter() - started) * 1_000,
            None,
        )

    certificate_id = str(manifest["certificate_id"])
    if context.plant_model_id != PARAMETERIZED_PLANT_MODEL_ID:
        return CertificateCoverageResult(
            CertificateStatus.INCOMPATIBLE_CONTEXT,
            ("context plant model does not match the proved certificate model",),
            (time.perf_counter() - started) * 1_000,
            certificate_id,
        )
    if context.recovery_policy_id != PARAMETERIZED_POLICY_ID:
        return CertificateCoverageResult(
            CertificateStatus.INCOMPATIBLE_CONTEXT,
            ("context recovery policy does not match the proved fixed takeover policy",),
            (time.perf_counter() - started) * 1_000,
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
    if not (plant.low_t1 <= state.x1 <= plant.high_t1 and plant.low_t2 <= state.x2 <= plant.high_t2):
        reasons.append("current tank state is outside the certified closed safety region")
    if plant.primary_capacity < 0:
        reasons.append("certificate requires nonnegative primary capacity")
    if plant.backup_capacity < plant.min_service_flow or plant.min_service_flow <= 0:
        reasons.append("backup capacity does not establish the certified positive delivered service")
    if plant.backup_startup_delay <= 0 or plant.backup_startup_delay > plant.service_deadline:
        reasons.append("startup delay is outside the certified positive deadline-bounded range")
    if plant.control_period <= 0:
        reasons.append("post-takeover operation duration must be positive")
    if plant.isolation_delay != 0:
        reasons.append("certificate requires immediate effective trusted isolation")
    if plant.upstream_nominal != plant.downstream_demand or plant.backup_capacity != plant.upstream_nominal:
        reasons.append("certificate requires balanced nominal inflow, demand, and backup flow")
    if assurance.intervention_budget < assurance.isolation_cost + assurance.backup_activation_cost:
        reasons.append("intervention budget does not cover trusted isolation plus backup activation")
    if reasons:
        return _not_covered(reasons, started, certificate_id)
    return CertificateCoverageResult(
        CertificateStatus.COVERED_BY_CERTIFICATE,
        ("validated context satisfies every assumption of the reviewed symbolic takeover theorem",),
        (time.perf_counter() - started) * 1_000,
        certificate_id,
    )
