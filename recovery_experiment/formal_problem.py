"""Deterministic incident-to-formal-problem construction for bounded schedules.

This module selects a formal *problem shape* from validated incident facts. It
does not run CLEO, discover a policy, or make a certificate claim merely because
an envelope can be constructed.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, replace
from enum import Enum
from pathlib import Path

from .certificate import CertificateCoverageResult
from .context import RecoveryContext
from .controlled_safe_hold_certificate import (
    CERTIFICATE_ID as CONTROLLED_SAFE_HOLD_CERTIFICATE_ID,
    check_controlled_safe_hold_recovery,
    reviewed_controlled_safe_hold_artifact_available,
)
from .controlled_safe_hold_formal import (
    CONTROLLED_SAFE_HOLD_MODEL_ID,
    CONTROLLED_SAFE_HOLD_PLANT_MODEL_ID,
    CONTROLLED_SAFE_HOLD_POLICY_ID,
    CONTROLLED_SAFE_HOLD_PROOF_PROFILE_ID,
)
from .delayed_isolation_certificate import CERTIFICATE_ID as DELAYED_ISOLATION_CERTIFICATE_ID
from .delayed_isolation_certificate import check_delayed_isolation_recovery
from .delayed_isolation_formal import (
    DELAYED_ISOLATION_MODEL_ID,
    DELAYED_ISOLATION_PLANT_MODEL_ID,
    DELAYED_ISOLATION_POLICY_ID,
)
from .delayed_isolation_proof_profile import DELAYED_ISOLATION_PROOF_PROFILE_ID
from .intermediate_delay_certificate import (
    CERTIFICATE_ID as INTERMEDIATE_DELAY_CERTIFICATE_ID,
    check_intermediate_delay_recovery,
    reviewed_intermediate_artifact_available,
)
from .intermediate_delay_formal import (
    INTERMEDIATE_DELAY_PLANT_MODEL_ID,
    INTERMEDIATE_DELAY_POLICY_ID,
)
from .recovery_model_builder import (
    INTERMEDIATE_DELAY_MODEL_ID,
    INTERMEDIATE_DELAY_PROOF_PROFILE_ID,
    BuildStatus,
    IsolationMode as BuilderIsolationMode,
    build_recovery_problem,
)
from .state_dependent_certificate import check_state_dependent_recovery
from .state_dependent_formal import (
    STATE_DEPENDENT_MODEL_ID,
    STATE_DEPENDENT_PLANT_MODEL_ID,
    STATE_DEPENDENT_POLICY_ID,
)
from .recovery_templates import (
    RecoveryTemplateId,
    TemplateApplicability,
    TemplateApplicabilityReport,
    assess_recovery_template_applicability,
)


class IncidentIsolationMode(str, Enum):
    IMMEDIATE = "immediate_effective_isolation"
    DELAYED = "bounded_delayed_effective_isolation"


class ConstructionStatus(str, Enum):
    CONSTRUCTED = "FORMAL_PROBLEM_CONSTRUCTED"
    INVALID_CONTEXT = "INVALID_INCIDENT_CONTEXT"
    UNSUPPORTED_CONFIGURATION = "UNSUPPORTED_INCIDENT_CONFIGURATION"


class ArtifactStatus(str, Enum):
    """Keep construction, reviewed proof artifacts, and coverage distinct."""

    MATCHING_VERIFIED_ARTIFACT_FOUND = "MATCHING_VERIFIED_ARTIFACT_FOUND"
    FORMAL_PROBLEM_UNVERIFIED = "FORMAL_PROBLEM_UNVERIFIED"
    NO_MATCHING_ARTIFACT = "NO_MATCHING_VERIFIED_ARTIFACT"


class TheoremStatus(str, Enum):
    VERIFIED = "FORMAL_THEOREM_VERIFIED"
    UNVERIFIED = "FORMAL_PROBLEM_UNVERIFIED"
    # Certificate review is deliberately represented separately below.
    REVIEWED_VERIFIED = VERIFIED
    NOT_REVIEWED = UNVERIFIED


class CertificateReviewStatus(str, Enum):
    ISSUED = "CERTIFICATE_ISSUED"
    REVIEW_REQUIRED = "CERTIFICATE_REVIEW_REQUIRED"


@dataclass(frozen=True)
class FormalProblemConstruction:
    status: ConstructionStatus
    isolation_mode: IncidentIsolationMode | None
    formal_model_id: str | None
    plant_model_id: str | None
    recovery_policy_id: str | None
    proof_profile: str | None
    certificate_id: str | None
    certificate_theorem_verified: bool
    reasons: tuple[str, ...]
    artifact_status: ArtifactStatus | None = None
    generated_phase_count: int = 0
    generated_safety_margins: tuple[str, ...] = ()
    theorem_status: TheoremStatus = TheoremStatus.NOT_REVIEWED
    certificate_review_status: CertificateReviewStatus = CertificateReviewStatus.REVIEW_REQUIRED

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["status"] = self.status.value
        data["isolation_mode"] = None if self.isolation_mode is None else self.isolation_mode.value
        data["artifact_status"] = None if self.artifact_status is None else self.artifact_status.value
        data["theorem_status"] = self.theorem_status.value
        data["certificate_review_status"] = self.certificate_review_status.value
        data["reasons"] = list(self.reasons)
        data["generated_safety_margins"] = list(self.generated_safety_margins)
        return data


@dataclass(frozen=True)
class IncidentFormalAssessment:
    construction: FormalProblemConstruction
    certificate: CertificateCoverageResult | None
    local_latency_ms: float

    def as_dict(self) -> dict[str, object]:
        return {
            "construction": self.construction.as_dict(),
            "certificate": None if self.certificate is None else self.certificate.as_dict(),
            "local_latency_ms": self.local_latency_ms,
        }


@dataclass(frozen=True)
class TemplateFormalProblem:
    """Construction and authorization status for one explicitly applicable template."""

    template_id: RecoveryTemplateId
    applicability: TemplateApplicability
    construction: FormalProblemConstruction | None
    certificate: CertificateCoverageResult | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "template_id": self.template_id.value,
            "template_applicability": self.applicability.as_dict(),
            "construction": None if self.construction is None else self.construction.as_dict(),
            "certificate": None if self.certificate is None else self.certificate.as_dict(),
        }


@dataclass(frozen=True)
class TemplateFormalProblemAssessment:
    """Keep applicability, construction, theorem review, and coverage separate."""

    applicability: TemplateApplicabilityReport
    templates: tuple[TemplateFormalProblem, ...]
    local_latency_ms: float

    def as_dict(self) -> dict[str, object]:
        return {
            "template_applicability": self.applicability.as_dict(),
            "templates": [template.as_dict() for template in self.templates],
            "local_latency_ms": self.local_latency_ms,
        }


def _recorded_bounded_theorem_is_verified(isolation_periods: int, startup_periods: int) -> bool:
    """Read local *unreviewed* proof evidence for reporting, never authorization.

    The runtime selection path does not call this helper. A record distinguishes
    an offline-checked theorem from one merely rendered, but is not provenance.
    """

    if isolation_periods <= 0:
        return False
    path = (
        Path(__file__).resolve().parent
        / "proof_records"
        / f"bounded_{isolation_periods}t{startup_periods}"
        / "bounded_delay_verification.json"
    )
    try:
        evidence = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    expected_model = (
        f"built-{isolation_periods}of{startup_periods}-control-period-isolation-flowing-takeover-v1"
    )
    obligations = evidence.get("obligations")
    return (
        evidence.get("status") == "VERIFIED"
        and evidence.get("schedule")
        == {
            "control_period": 0.5,
            "isolation_periods": isolation_periods,
            "startup_periods": startup_periods,
        }
        and evidence.get("formal_model_id") == expected_model
        and isinstance(obligations, list)
        and bool(obligations)
        and all(obligation.get("passed") is True for obligation in obligations)
    )


def construct_formal_problem(context: RecoveryContext) -> FormalProblemConstruction:
    """Construct the typed recovery phases before looking up assurance artifacts."""

    built = build_recovery_problem(context)
    if built.status is BuildStatus.INVALID_CONTEXT:
        return FormalProblemConstruction(
            ConstructionStatus.INVALID_CONTEXT,
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            built.reasons,
            ArtifactStatus.NO_MATCHING_ARTIFACT,
        )
    if built.status is not BuildStatus.CONSTRUCTED or built.spec is None:
        return FormalProblemConstruction(
            ConstructionStatus.UNSUPPORTED_CONFIGURATION,
            IncidentIsolationMode.DELAYED if context.plant.isolation_delay > 0 else None,
            None,
            None,
            None,
            None,
            None,
            False,
            built.reasons,
            ArtifactStatus.NO_MATCHING_ARTIFACT,
        )
    if (
        built.spec.isolation_mode is not BuilderIsolationMode.IMMEDIATE
        and context.plant.backup_capacity < context.plant.min_service_flow
    ):
        return FormalProblemConstruction(
            ConstructionStatus.UNSUPPORTED_CONFIGURATION,
            IncidentIsolationMode.DELAYED if built.spec.isolation_mode is not BuilderIsolationMode.IMMEDIATE else IncidentIsolationMode.IMMEDIATE,
            built.spec.plant_model_id,
            None,
            built.spec.recovery_policy_id,
            built.spec.proof_profile_id,
            None,
            False,
            (
                "the selected formal contract requires qbackup >= qmin; configured backup capacity is below "
                "the required minimum delivered flow",
            ),
            ArtifactStatus.NO_MATCHING_ARTIFACT,
            len(built.phases),
            built.spec.margins.as_tuple(),
        )
    if built.spec.schedule.isolation_periods == 0 and built.matching_verified_artifact:
        return FormalProblemConstruction(
            ConstructionStatus.CONSTRUCTED,
            IncidentIsolationMode.IMMEDIATE,
            STATE_DEPENDENT_MODEL_ID,
            STATE_DEPENDENT_PLANT_MODEL_ID,
            STATE_DEPENDENT_POLICY_ID,
            "state_dependent_proof_profile.attach_state_dependent_profile",
            "two-tank-flowing-takeover-state-dependent-v1",
            built.matching_verified_artifact,
            built.reasons,
            (
                ArtifactStatus.MATCHING_VERIFIED_ARTIFACT_FOUND
                if built.matching_verified_artifact
                else ArtifactStatus.NO_MATCHING_ARTIFACT
            ),
            len(built.phases),
            built.spec.margins.as_tuple(),
            TheoremStatus.VERIFIED,
            CertificateReviewStatus.ISSUED,
        )
    if built.spec.schedule.isolation_periods == 1 and built.spec.schedule.startup_periods == 3:
        reviewed = reviewed_intermediate_artifact_available()
        return FormalProblemConstruction(
            ConstructionStatus.CONSTRUCTED,
            IncidentIsolationMode.DELAYED,
            INTERMEDIATE_DELAY_MODEL_ID,
            INTERMEDIATE_DELAY_PLANT_MODEL_ID,
            INTERMEDIATE_DELAY_POLICY_ID,
            INTERMEDIATE_DELAY_PROOF_PROFILE_ID,
            INTERMEDIATE_DELAY_CERTIFICATE_ID if reviewed else None,
            reviewed,
            (
                "one-control-period delayed game was generated from typed phases",
                "reviewed generated 1T manifest matches the deterministic formal artifact"
                if reviewed
                else "the generated 1T theorem has no usable reviewed certificate manifest",
            ),
            ArtifactStatus.MATCHING_VERIFIED_ARTIFACT_FOUND if reviewed else ArtifactStatus.FORMAL_PROBLEM_UNVERIFIED,
            len(built.phases),
            built.spec.margins.as_tuple(),
            TheoremStatus.VERIFIED if reviewed else TheoremStatus.UNVERIFIED,
            CertificateReviewStatus.ISSUED if reviewed else CertificateReviewStatus.REVIEW_REQUIRED,
        )
    if built.spec.schedule.isolation_periods == 2 and built.matching_verified_artifact:
        return FormalProblemConstruction(
            ConstructionStatus.CONSTRUCTED,
            IncidentIsolationMode.DELAYED,
            DELAYED_ISOLATION_MODEL_ID,
            DELAYED_ISOLATION_PLANT_MODEL_ID,
            DELAYED_ISOLATION_POLICY_ID,
            DELAYED_ISOLATION_PROOF_PROFILE_ID,
            DELAYED_ISOLATION_CERTIFICATE_ID,
            built.matching_verified_artifact,
            built.reasons,
            (
                ArtifactStatus.MATCHING_VERIFIED_ARTIFACT_FOUND
                if built.matching_verified_artifact
                else ArtifactStatus.NO_MATCHING_ARTIFACT
            ),
            len(built.phases),
            built.spec.margins.as_tuple(),
            TheoremStatus.VERIFIED,
            CertificateReviewStatus.ISSUED,
        )
    theorem_verified = _recorded_bounded_theorem_is_verified(
        built.spec.schedule.isolation_periods,
        built.spec.schedule.startup_periods,
    )
    return FormalProblemConstruction(
        ConstructionStatus.CONSTRUCTED,
        IncidentIsolationMode.DELAYED if built.spec.schedule.isolation_periods > 0 else IncidentIsolationMode.IMMEDIATE,
        built.formal_model_id,
        "bounded-isolation-state-dependent-two-tank-v1",
        built.spec.recovery_policy_id,
        built.spec.proof_profile_id,
        None,
        False,
        (
            "bounded schedule was generated from typed phases",
            (
                "a local CLEO proof record is available, but separate reviewed certificate provenance is required "
                "before runtime authorization"
                if theorem_verified
                else "no matching successful local CLEO proof record is available; separate reviewed certificate provenance "
                "would still be required before runtime authorization"
            ),
        ),
        ArtifactStatus.FORMAL_PROBLEM_UNVERIFIED,
        len(built.phases),
        built.spec.margins.as_tuple(),
        TheoremStatus.VERIFIED if theorem_verified else TheoremStatus.UNVERIFIED,
        CertificateReviewStatus.REVIEW_REQUIRED,
    )


def assess_incident_formal_problem(context: RecoveryContext) -> IncidentFormalAssessment:
    """Keep construction and certificate applicability as explicitly separate results."""

    started = time.perf_counter()
    construction = construct_formal_problem(context)
    certificate: CertificateCoverageResult | None = None
    if construction.status is ConstructionStatus.CONSTRUCTED and construction.formal_model_id == STATE_DEPENDENT_MODEL_ID:
        immediate_context = replace(
            context,
            plant_model_id=STATE_DEPENDENT_PLANT_MODEL_ID,
            recovery_policy_id=STATE_DEPENDENT_POLICY_ID,
        )
        certificate = check_state_dependent_recovery(immediate_context)
    elif construction.status is ConstructionStatus.CONSTRUCTED and construction.formal_model_id == INTERMEDIATE_DELAY_MODEL_ID:
        intermediate_context = replace(
            context,
            plant_model_id=INTERMEDIATE_DELAY_PLANT_MODEL_ID,
            recovery_policy_id=INTERMEDIATE_DELAY_POLICY_ID,
        )
        certificate = check_intermediate_delay_recovery(intermediate_context)
    elif (
        construction.status is ConstructionStatus.CONSTRUCTED
        and construction.formal_model_id == DELAYED_ISOLATION_MODEL_ID
    ):
        delayed_context = replace(
            context,
            plant_model_id=DELAYED_ISOLATION_PLANT_MODEL_ID,
            recovery_policy_id=DELAYED_ISOLATION_POLICY_ID,
        )
        certificate = check_delayed_isolation_recovery(delayed_context)
    return IncidentFormalAssessment(
        construction,
        certificate,
        (time.perf_counter() - started) * 1_000,
    )


def _controlled_safe_hold_construction(
    applicability: TemplateApplicability,
) -> FormalProblemConstruction:
    """Describe the distinct hold theorem without calling its runtime checker."""

    reviewed = reviewed_controlled_safe_hold_artifact_available()
    return FormalProblemConstruction(
        ConstructionStatus.CONSTRUCTED,
        IncidentIsolationMode.IMMEDIATE,
        CONTROLLED_SAFE_HOLD_MODEL_ID,
        CONTROLLED_SAFE_HOLD_PLANT_MODEL_ID,
        CONTROLLED_SAFE_HOLD_POLICY_ID,
        CONTROLLED_SAFE_HOLD_PROOF_PROFILE_ID,
        CONTROLLED_SAFE_HOLD_CERTIFICATE_ID if reviewed else None,
        reviewed,
        (
            "controlled safe hold is a separate resource-dependent formal problem",
            "the attacker selects P1 before immediate trusted isolation; no P1-effective hold evolution is modeled",
            "trusted upstream and downstream gates set qin=qout=qdelivered=0 while external demand remains explicit",
            "one mandatory HoldDuration > 0 ODE is proved independently of P2 availability",
        ),
        ArtifactStatus.MATCHING_VERIFIED_ARTIFACT_FOUND if reviewed else ArtifactStatus.FORMAL_PROBLEM_UNVERIFIED,
        len(applicability.template.phase_structure),
        ("L1 <= x1 <= H1", "L2 <= x2 <= H2", "HoldDuration > 0"),
        TheoremStatus.VERIFIED if reviewed else TheoremStatus.UNVERIFIED,
        CertificateReviewStatus.ISSUED if reviewed else CertificateReviewStatus.REVIEW_REQUIRED,
    )


def construct_template_formal_problems(context: RecoveryContext) -> tuple[TemplateFormalProblem, ...]:
    """Construct each resource-compatible theorem shape independently.

    This function deliberately does not collapse unavailable resources into a
    timing value. Template A reuses the existing generated `(n,m)` flowing
    takeover builder. Template B constructs the separate finite safe-hold game.
    """

    report = assess_recovery_template_applicability(context)
    problems: list[TemplateFormalProblem] = []
    for applicability in report.entries:
        if not applicability.applicable:
            problems.append(TemplateFormalProblem(applicability.template.template_id, applicability, None))
        elif applicability.template.template_id is RecoveryTemplateId.FLOWING_BACKUP_TAKEOVER:
            problems.append(
                TemplateFormalProblem(
                    applicability.template.template_id,
                    applicability,
                    construct_formal_problem(context),
                )
            )
        elif applicability.template.template_id is RecoveryTemplateId.CONTROLLED_SAFE_HOLD:
            problems.append(
                TemplateFormalProblem(
                    applicability.template.template_id,
                    applicability,
                    _controlled_safe_hold_construction(applicability),
                )
            )
        else:  # pragma: no cover - keeps future template additions explicit.
            raise RuntimeError(f"unknown recovery template {applicability.template.template_id}")
    return tuple(problems)


def assess_template_formal_problems(context: RecoveryContext) -> TemplateFormalProblemAssessment:
    """Add runtime certificate coverage after independent problem construction."""

    started = time.perf_counter()
    report = assess_recovery_template_applicability(context)
    assessed: list[TemplateFormalProblem] = []
    for problem in construct_template_formal_problems(context):
        certificate: CertificateCoverageResult | None = None
        if problem.construction is not None and problem.construction.status is ConstructionStatus.CONSTRUCTED:
            if problem.template_id is RecoveryTemplateId.FLOWING_BACKUP_TAKEOVER:
                certificate = assess_incident_formal_problem(context).certificate
            elif problem.template_id is RecoveryTemplateId.CONTROLLED_SAFE_HOLD:
                certificate = check_controlled_safe_hold_recovery(
                    replace(
                        context,
                        plant_model_id=CONTROLLED_SAFE_HOLD_PLANT_MODEL_ID,
                        recovery_policy_id=CONTROLLED_SAFE_HOLD_POLICY_ID,
                    )
                )
        assessed.append(
            TemplateFormalProblem(
                problem.template_id,
                problem.applicability,
                problem.construction,
                certificate,
            )
        )
    return TemplateFormalProblemAssessment(report, tuple(assessed), (time.perf_counter() - started) * 1_000)
