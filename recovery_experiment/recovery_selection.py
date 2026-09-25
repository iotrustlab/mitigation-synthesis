"""Select among reviewed recovery policies compatible with one common incident.

This module compares a finite policy set using existing offline certificates.
It does not synthesize a controller, invoke CLEO, or command an actuator.
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass, replace
from enum import Enum
from pathlib import Path

from .certificate import CertificateCoverageResult, CertificateStatus
from .common_horizon import CommonFormalHorizon, derive_common_formal_horizon
from .controlled_safe_hold_certificate import check_controlled_safe_hold_recovery
from .controlled_safe_hold_formal import (
    CONTROLLED_SAFE_HOLD_MODEL_ID,
    CONTROLLED_SAFE_HOLD_PLANT_MODEL_ID,
    CONTROLLED_SAFE_HOLD_POLICY_ID,
)
from .context import ContextValidationError, RecoveryContext
from .cost import RecoveryCost, calculate_cost
from .delayed_isolation_certificate import check_delayed_isolation_recovery
from .delayed_isolation_formal import (
    DELAYED_ISOLATION_MODEL_ID,
    DELAYED_ISOLATION_PLANT_MODEL_ID,
    DELAYED_ISOLATION_POLICY_ID,
)
from .intermediate_delay_certificate import (
    check_intermediate_delay_recovery,
    reviewed_intermediate_artifact_available,
)
from .intermediate_delay_formal import (
    INTERMEDIATE_DELAY_PLANT_MODEL_ID,
    INTERMEDIATE_DELAY_POLICY_ID,
)
from .experiment import run_scenario
from .model import AttackerAction, PlantParameters
from .policies import (
    PersistentPrimaryAttacker,
    ScheduledPrimaryAttacker,
    TrustedControlledSafeHoldPolicy,
    TrustedDelayedIsolationFlowingBackupTakeoverPolicy,
    TrustedFlowingBackupTakeoverPolicy,
)
from .recovery_model_builder import (
    INTERMEDIATE_DELAY_MODEL_ID,
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
    CONTROLLED_SAFE_HOLD_TEMPLATE_ID,
    RecoveryTemplateId,
    TemplateApplicabilityReport,
    assess_recovery_template_applicability,
)


COMMON_TOPOLOGY_ID = "synthetic-parallel-pump-two-tank-incident-v1"
CONTROLLED_SAFE_HOLD = CONTROLLED_SAFE_HOLD_TEMPLATE_ID
# Compatibility name for callers of the former P2-backed "controlled hold".
# It now names the separate safe-hold template rather than a backup takeover.
CONTROLLED_HOLD = CONTROLLED_SAFE_HOLD
FLOWING_TAKEOVER = "flowing_backup_takeover"
DELAYED_FLOWING_TAKEOVER = "delayed_isolation_flowing_backup_takeover"
INTERMEDIATE_FLOWING_TAKEOVER = "one_control_period_isolation_flowing_backup_takeover"


class SelectionStatus(str, Enum):
    ADMISSIBLE = "COVERED_AND_REQUIREMENTS_SATISFIED"
    COVERED_SERVICE_INADEQUATE = "COVERED_BUT_REQUESTED_SERVICE_NOT_ESTABLISHED"
    NOT_COVERED = "NOT_COVERED_BY_CERTIFICATE"
    INVALID_OR_INCOMPATIBLE = "INVALID_OR_INCOMPATIBLE_CONTEXT"
    UNTRUSTED = "UNTRUSTED_OR_UNAVAILABLE_CERTIFICATE"
    FORMAL_GUARANTEE_UNAVAILABLE = "FORMAL_GUARANTEE_UNAVAILABLE_OR_UNRESOLVED"


class RecoverySelectionStatus(str, Enum):
    SELECTED = "RECOVERY_TEMPLATE_SELECTED"
    NO_SUPPORTED_TEMPLATE = "NO_SUPPORTED_RECOVERY_TEMPLATE"
    NO_ADMISSIBLE_CANDIDATE = "NO_FORMALLY_ADMISSIBLE_CANDIDATE"
    INVALID_INCIDENT = "INVALID_INCIDENT_CONTEXT"


@dataclass(frozen=True)
class IncidentServiceContract:
    """Requirements evaluated identically for every candidate policy."""

    external_demand: float
    required_delivered_flow: float
    require_continuous_delivery: bool
    permitted_interruption_duration: float
    recovery_deadline: float
    assured_operation_duration: float
    evaluation_horizon: float

    def validate(self, plant: PlantParameters) -> None:
        values = {
            "external_demand": self.external_demand,
            "required_delivered_flow": self.required_delivered_flow,
            "permitted_interruption_duration": self.permitted_interruption_duration,
            "recovery_deadline": self.recovery_deadline,
            "assured_operation_duration": self.assured_operation_duration,
            "evaluation_horizon": self.evaluation_horizon,
        }
        positive_values = {
            name: value
            for name, value in values.items()
            if name not in {"required_delivered_flow", "permitted_interruption_duration"}
        }
        if any(not math.isfinite(value) or value <= 0 for value in positive_values.values()):
            raise ValueError("incident service values other than delivery and interruption allowance must be finite and positive")
        if not math.isfinite(self.required_delivered_flow) or self.required_delivered_flow < 0:
            raise ValueError("required delivered flow must be finite and nonnegative")
        if self.require_continuous_delivery and self.required_delivered_flow <= 0:
            raise ValueError("continuous delivery requires a positive required delivered flow")
        if not math.isfinite(self.permitted_interruption_duration) or self.permitted_interruption_duration < 0:
            raise ValueError("permitted interruption duration must be finite and nonnegative")
        if self.require_continuous_delivery and self.permitted_interruption_duration != 0:
            raise ValueError("continuous delivery requires zero permitted interruption duration")
        if self.required_delivered_flow > self.external_demand:
            raise ValueError("required delivered flow cannot exceed external demand")
        if self.external_demand != plant.downstream_demand:
            raise ValueError("external demand must match the one common plant demand configuration")
        if self.evaluation_horizon != plant.horizon:
            raise ValueError("incident evaluation horizon must match the common plant horizon")
        horizon = derive_common_formal_horizon(plant, self.evaluation_horizon)
        if self.assured_operation_duration > horizon.post_takeover_operation_duration:
            raise ValueError("requested post-recovery duration exceeds the common finite evaluation horizon")


@dataclass(frozen=True)
class RecoveryIncident:
    """One policy-neutral incident projected into each reviewed certificate model."""

    context: RecoveryContext
    service: IncidentServiceContract
    topology_id: str = COMMON_TOPOLOGY_ID
    attacker_schedule: tuple[AttackerAction, ...] | None = None

    def validate(self) -> None:
        self.context.validate()
        self.service.validate(self.context.plant)


@dataclass(frozen=True)
class CertificatePaths:
    """Optional paths are for diagnostics; checkers authorize only their canonical manifests."""

    controlled_safe_hold: Path | None = None
    # Deprecated diagnostic alias retained for callers of the old selection API.
    controlled_hold: Path | None = None
    flowing_takeover: Path | None = None
    intermediate_flowing_takeover: Path | None = None
    delayed_flowing_takeover: Path | None = None


@dataclass(frozen=True)
class FormalGuarantee:
    formal_model_id: str
    recovery_policy_id: str
    safety_throughout: bool
    startup_delivery_lower_bound: float
    post_takeover_delivery_lower_bound: float
    transfer_recovery_time: float
    assured_operation_duration: float
    formal_horizon: CommonFormalHorizon
    startup_interruption_duration: float
    continuous_delivery_established: bool
    description: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PolicySelectionResult:
    policy: str
    status: SelectionStatus
    certificate: CertificateCoverageResult
    guarantee: FormalGuarantee
    reasons: tuple[str, ...]
    trace: dict[str, object] | None
    cost: RecoveryCost | None
    cost_comparable: bool

    @property
    def admissible(self) -> bool:
        return self.status is SelectionStatus.ADMISSIBLE

    def as_dict(self) -> dict[str, object]:
        return {
            "policy": self.policy,
            "status": self.status.value,
            "admissible": self.admissible,
            "certificate": self.certificate.as_dict(),
            "guarantee": self.guarantee.as_dict(),
            "reasons": list(self.reasons),
            "trace": self.trace,
            "cost": None if self.cost is None else self.cost.as_dict(),
            "cost_interpretation": {
                "estimated_before_selection": None if self.cost is None else self.cost.as_dict(),
                "observed_from_completed_simulation": None if self.cost is None else self.cost.as_dict(),
                "formal_cost_bound": None,
                "note": (
                    "The estimate is computed from a completed deterministic simulation of this candidate. "
                    "It is not a formally proved bound or a physical deployment measurement."
                    if self.cost is not None
                    else "No cost estimate is exposed because this candidate did not first pass certificate and service-contract admissibility."
                ),
            },
            "cost_comparable": self.cost_comparable,
        }


@dataclass(frozen=True)
class RecoverySelection:
    incident: RecoveryIncident
    template_applicability: TemplateApplicabilityReport
    candidates: tuple[PolicySelectionResult, ...]
    selected_policy: str | None
    status: RecoverySelectionStatus
    selection_reason: str
    certificate_and_admissibility_latency_ms: float
    simulation_and_cost_latency_ms: float
    total_local_latency_ms: float

    def as_dict(self) -> dict[str, object]:
        return {
            "incident": {
                "topology_id": self.incident.topology_id,
                "context": self.incident.context.as_dict(),
                "service": asdict(self.incident.service),
                "attacker_schedule": None
                if self.incident.attacker_schedule is None
                else [action.value for action in self.incident.attacker_schedule],
            },
            "template_applicability": self.template_applicability.as_dict(),
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "selected_policy": self.selected_policy,
            "status": self.status.value,
            "selection_reason": self.selection_reason,
            "latency_ms": {
                "certificate_and_admissibility": self.certificate_and_admissibility_latency_ms,
                "simulation_and_cost": self.simulation_and_cost_latency_ms,
                "total_local": self.total_local_latency_ms,
            },
            "offline_proof_note": "Offline CLEO proof time is not included in local selection latency.",
        }


def incident_from_context(
    context: RecoveryContext,
    *,
    required_delivered_flow: float | None = None,
    require_continuous_delivery: bool,
    permitted_interruption_duration: float | None = None,
    recovery_deadline: float | None = None,
    assured_operation_duration: float | None = None,
    topology_id: str = COMMON_TOPOLOGY_ID,
    attacker_schedule: tuple[AttackerAction, ...] | None = None,
) -> RecoveryIncident:
    """Create a common incident without changing the source context's policy identity."""

    plant = context.plant
    return RecoveryIncident(
        context=context,
        service=IncidentServiceContract(
            external_demand=plant.downstream_demand,
            required_delivered_flow=(
                plant.min_service_flow if required_delivered_flow is None else required_delivered_flow
            ),
            require_continuous_delivery=require_continuous_delivery,
            recovery_deadline=(
                plant.transfer_recovery_deadline if recovery_deadline is None else recovery_deadline
            ),
            assured_operation_duration=(
                plant.horizon - plant.backup_startup_delay
                if assured_operation_duration is None
                else assured_operation_duration
            ),
            evaluation_horizon=plant.horizon,
            permitted_interruption_duration=(
                0.0
                if require_continuous_delivery
                else (
                    plant.backup_startup_delay
                    if permitted_interruption_duration is None
                    else permitted_interruption_duration
                )
            ),
        ),
        topology_id=topology_id,
        attacker_schedule=attacker_schedule,
    )


def _project_context(incident: RecoveryIncident, policy: str) -> RecoveryContext:
    """Bind the same incident facts to a certificate's explicit identity pair."""

    if policy == CONTROLLED_SAFE_HOLD:
        return replace(
            incident.context,
            plant_model_id=CONTROLLED_SAFE_HOLD_PLANT_MODEL_ID,
            recovery_policy_id=CONTROLLED_SAFE_HOLD_POLICY_ID,
        )
    if policy == FLOWING_TAKEOVER:
        return replace(
            incident.context,
            plant_model_id=STATE_DEPENDENT_PLANT_MODEL_ID,
            recovery_policy_id=STATE_DEPENDENT_POLICY_ID,
        )
    if policy == DELAYED_FLOWING_TAKEOVER:
        return replace(
            incident.context,
            plant_model_id=DELAYED_ISOLATION_PLANT_MODEL_ID,
            recovery_policy_id=DELAYED_ISOLATION_POLICY_ID,
        )
    if policy == INTERMEDIATE_FLOWING_TAKEOVER:
        return replace(
            incident.context,
            plant_model_id=INTERMEDIATE_DELAY_PLANT_MODEL_ID,
            recovery_policy_id=INTERMEDIATE_DELAY_POLICY_ID,
        )
    raise ValueError(f"unsupported recovery policy: {policy}")


def _guarantee(
    policy: str, plant: PlantParameters, evaluation_horizon: float
) -> FormalGuarantee:
    if policy == CONTROLLED_SAFE_HOLD:
        # The safe-hold game has one mandatory HoldDuration ODE, unlike the
        # backup theorem's startup-plus-operation timeline.
        horizon = CommonFormalHorizon(0.0, evaluation_horizon, evaluation_horizon)
        return FormalGuarantee(
            formal_model_id=CONTROLLED_SAFE_HOLD_MODEL_ID,
            recovery_policy_id=CONTROLLED_SAFE_HOLD_POLICY_ID,
            safety_throughout=True,
            startup_delivery_lower_bound=0.0,
            post_takeover_delivery_lower_bound=0.0,
            transfer_recovery_time=0.0,
            assured_operation_duration=evaluation_horizon,
            formal_horizon=horizon,
            startup_interruption_duration=evaluation_horizon,
            continuous_delivery_established=False,
            description=(
                "Certificate proves finite-horizon safety after immediate independent isolation and trusted gate "
                "closure. External demand remains positive, while qdelivered is intentionally zero for the full hold."
            ),
        )
    horizon = derive_common_formal_horizon(plant, evaluation_horizon)
    if policy == FLOWING_TAKEOVER:
        return FormalGuarantee(
            formal_model_id=STATE_DEPENDENT_MODEL_ID,
            recovery_policy_id=STATE_DEPENDENT_POLICY_ID,
            safety_throughout=True,
            startup_delivery_lower_bound=plant.startup_withdrawal_rate,
            post_takeover_delivery_lower_bound=plant.backup_capacity,
            transfer_recovery_time=plant.backup_startup_delay,
            assured_operation_duration=horizon.post_takeover_operation_duration,
            formal_horizon=horizon,
            startup_interruption_duration=0.0,
            continuous_delivery_established=True,
            description=(
                "Certificate proves safety and qdelivered=qout=startupWithdrawal during startup, then "
                "balanced backup delivery for one mandatory post-takeover interval."
            ),
        )
    if policy not in {INTERMEDIATE_FLOWING_TAKEOVER, DELAYED_FLOWING_TAKEOVER}:
        raise ValueError(f"unsupported recovery policy: {policy}")
    one_period = policy == INTERMEDIATE_FLOWING_TAKEOVER
    return FormalGuarantee(
        formal_model_id=(
            INTERMEDIATE_DELAY_MODEL_ID
            if one_period
            else DELAYED_ISOLATION_MODEL_ID
        ),
        recovery_policy_id=INTERMEDIATE_DELAY_POLICY_ID if one_period else DELAYED_ISOLATION_POLICY_ID,
        safety_throughout=True,
        startup_delivery_lower_bound=plant.startup_withdrawal_rate,
        post_takeover_delivery_lower_bound=plant.backup_capacity,
        transfer_recovery_time=plant.backup_startup_delay,
        assured_operation_duration=horizon.post_takeover_operation_duration,
        formal_horizon=horizon,
        startup_interruption_duration=0.0,
        continuous_delivery_established=True,
        description=(
            f"Certificate proves safety through {'one' if one_period else 'two'} Demon-controlled P1 command "
            "period(s) before trusted isolation, flowing qdelivered=qout=startupWithdrawal through P2 startup, "
            "then balanced backup delivery for one mandatory post-takeover interval."
        ),
    )


def _status_from_certificate(coverage: CertificateCoverageResult) -> SelectionStatus | None:
    if coverage.status is CertificateStatus.NOT_COVERED_BY_CERTIFICATE:
        return SelectionStatus.NOT_COVERED
    if coverage.status in {CertificateStatus.INVALID_CONTEXT, CertificateStatus.INCOMPATIBLE_CONTEXT}:
        return SelectionStatus.INVALID_OR_INCOMPATIBLE
    if coverage.status is CertificateStatus.UNTRUSTED_CERTIFICATE:
        return SelectionStatus.UNTRUSTED
    if coverage.status is CertificateStatus.UNVERIFIED:
        return SelectionStatus.FORMAL_GUARANTEE_UNAVAILABLE
    if coverage.status is CertificateStatus.COVERED_BY_CERTIFICATE:
        return None
    return SelectionStatus.FORMAL_GUARANTEE_UNAVAILABLE


def _requirement_reasons(guarantee: FormalGuarantee, service: IncidentServiceContract) -> list[str]:
    reasons: list[str] = []
    if guarantee.transfer_recovery_time > service.recovery_deadline:
        reasons.append("certificate does not establish recovery by the incident deadline")
    if guarantee.assured_operation_duration < service.assured_operation_duration:
        reasons.append("certificate's finite post-takeover interval is shorter than requested assurance")
    if guarantee.formal_horizon.total_duration < service.evaluation_horizon:
        reasons.append("certificate's finite horizon is shorter than the common evaluation horizon")
    if guarantee.startup_interruption_duration > service.permitted_interruption_duration:
        reasons.append("startup interruption is longer than the incident permits")
    if service.require_continuous_delivery:
        if not guarantee.continuous_delivery_established:
            reasons.append("controlled hold establishes zero delivery during startup, not uninterrupted service")
        elif guarantee.startup_delivery_lower_bound < service.required_delivered_flow:
            reasons.append("startup delivery guaranteed by the certificate is below required delivered flow")
    if guarantee.post_takeover_delivery_lower_bound < service.required_delivered_flow:
        reasons.append("post-takeover delivery guaranteed by the certificate is below required delivered flow")
    return reasons


def _trace_and_cost(
    incident: RecoveryIncident, policy: str, guarantee: FormalGuarantee, *, include_cost: bool
) -> tuple[dict[str, object], RecoveryCost | None]:
    plant = incident.context.plant
    if policy == CONTROLLED_SAFE_HOLD:
        defender = TrustedControlledSafeHoldPolicy()
        attacker = PersistentPrimaryAttacker(active_until=incident.service.evaluation_horizon)
        strategy = "controlled_safe_hold"
        schedule: tuple[AttackerAction, ...] | None = None
    elif policy == FLOWING_TAKEOVER:
        defender = TrustedFlowingBackupTakeoverPolicy()
        attacker = PersistentPrimaryAttacker(active_until=incident.service.evaluation_horizon)
        strategy = "trusted_flowing_backup_takeover"
        schedule = None
    elif policy in {INTERMEDIATE_FLOWING_TAKEOVER, DELAYED_FLOWING_TAKEOVER}:
        defender = TrustedDelayedIsolationFlowingBackupTakeoverPolicy()
        command_count = 1 if policy == INTERMEDIATE_FLOWING_TAKEOVER else 2
        # The theorem is universal over its binary choices. This fallback is a
        # diagnostic trace only and does not narrow certificate coverage.
        schedule = incident.attacker_schedule or tuple(AttackerAction.FORCE_PRIMARY_OFF for _ in range(command_count))
        attacker = ScheduledPrimaryAttacker(schedule)
        strategy = "trusted_delayed_isolation_flowing_backup_takeover"
    else:
        raise ValueError(f"unsupported recovery policy: {policy}")
    result = run_scenario(
        f"selection_{policy}",
        plant,
        attacker,
        defender,
        initial_state=incident.context.current_state,
    )
    required = incident.service.required_delivered_flow
    trace = {
        "simulated": True,
        "external_demand": incident.service.external_demand,
        "evaluation_horizon": incident.service.evaluation_horizon,
        "candidate_theorem_horizon": guarantee.formal_horizon.total_duration,
        "candidate_theorem_operation_duration": guarantee.assured_operation_duration,
        "attacker_schedule": None if schedule is None else [action.value for action in schedule],
        "attacker_schedule_scope": (
            "not applicable to the immediate-isolation diagnostic trace"
            if schedule is None
            else f"one deterministic {len(schedule)}-period schedule; theorem coverage remains universal over all binary pairs in the matching theorem"
        ),
        "safe": result.safe,
        "continuous_required_service_in_trace": all(
            row.q_delivered >= required for row in result.records
        ),
        "service_after_incident_deadline": all(
            row.q_delivered >= required
            for row in result.records
            if row.timestamp >= incident.service.recovery_deadline - 1e-12
        ),
        "service_after_legacy_general_deadline": result.service_satisfied_after_deadline,
        "recovery_established_at": result.final_state.recovery_established_at,
        "startup_delivery": [
            row.q_delivered
            for row in result.records
            if row.timestamp
            <= (
                incident.service.evaluation_horizon
                if policy == CONTROLLED_SAFE_HOLD
                else plant.backup_startup_delay
            )
            + 1e-12
        ],
    }
    cost = (
        calculate_cost(
            result,
            strategy,
            incident.context.recovery_cost_parameters,
            service_target=incident.service.external_demand,
        )
        if include_cost
        else None
    )
    return trace, cost


def _placeholder_certificate(status: CertificateStatus, reason: str, started: float) -> CertificateCoverageResult:
    return CertificateCoverageResult(status, (reason,), (time.perf_counter() - started) * 1_000, None)


def _applicable_policies(
    incident: RecoveryIncident,
    template_report: TemplateApplicabilityReport | None = None,
) -> tuple[str, ...]:
    """Map resource-compatible templates to reviewed timing-specific candidates."""

    template_report = template_report or assess_recovery_template_applicability(incident.context)
    applicable = set(template_report.applicable_templates)
    policies: list[str] = []
    if RecoveryTemplateId.CONTROLLED_SAFE_HOLD in applicable:
        policies.append(CONTROLLED_SAFE_HOLD)
    if RecoveryTemplateId.FLOWING_BACKUP_TAKEOVER not in applicable:
        return tuple(policies)
    generated = build_recovery_problem(incident.context)
    if generated.status is not BuildStatus.CONSTRUCTED or generated.spec is None:
        return tuple(policies)
    if generated.spec.schedule.isolation_periods == 0 and generated.matching_verified_artifact:
        policies.append(FLOWING_TAKEOVER)
        return tuple(policies)
    if (
        generated.spec.schedule.isolation_periods == 1
        and generated.spec.schedule.startup_periods == 3
        and reviewed_intermediate_artifact_available()
    ):
        policies.append(INTERMEDIATE_FLOWING_TAKEOVER)
        return tuple(policies)
    if generated.spec.schedule.isolation_periods == 2 and generated.matching_verified_artifact:
        policies.append(DELAYED_FLOWING_TAKEOVER)
        return tuple(policies)
    # Any generated schedule without separately reviewed provenance remains
    # non-authorizing, even if an offline proof attempt has succeeded.
    return tuple(policies)


def select_recovery_policy(
    incident: RecoveryIncident,
    *,
    certificate_paths: CertificatePaths = CertificatePaths(),
    simulate_for_diagnostics: bool = True,
) -> RecoverySelection:
    """Evaluate only policies compatible with an incident's isolation authority.

    Only candidates covered by their own certificate and satisfying the requested
    formal service/timing contract participate in cost selection.  Simulations
    are diagnostic and cost-estimation inputs, never a proof substitute.
    """

    total_started = time.perf_counter()
    template_report = assess_recovery_template_applicability(incident.context)
    validation_error: str | None = None
    try:
        incident.validate()
    except (ContextValidationError, ValueError) as exc:
        validation_error = str(exc)
    certificate_started = time.perf_counter()
    preliminary: list[tuple[str, SelectionStatus, CertificateCoverageResult, FormalGuarantee, tuple[str, ...]]] = []
    for policy in _applicable_policies(incident, template_report):
        try:
            guarantee = _guarantee(
                policy, incident.context.plant, incident.service.evaluation_horizon
            )
        except ValueError as exc:
            coverage = _placeholder_certificate(CertificateStatus.INVALID_CONTEXT, str(exc), certificate_started)
            placeholder_horizon = CommonFormalHorizon(0.0, 0.0, 0.0)
            guarantee = FormalGuarantee(
                formal_model_id="unavailable",
                recovery_policy_id="unavailable",
                safety_throughout=False,
                startup_delivery_lower_bound=0.0,
                post_takeover_delivery_lower_bound=0.0,
                transfer_recovery_time=0.0,
                assured_operation_duration=0.0,
                formal_horizon=placeholder_horizon,
                startup_interruption_duration=0.0,
                continuous_delivery_established=False,
                description="No formal guarantee is available because the common horizon is invalid.",
            )
            preliminary.append(
                (policy, SelectionStatus.INVALID_OR_INCOMPATIBLE, coverage, guarantee, (str(exc),))
            )
            continue
        if validation_error is not None:
            coverage = _placeholder_certificate(CertificateStatus.INVALID_CONTEXT, validation_error, certificate_started)
            preliminary.append(
                (policy, SelectionStatus.INVALID_OR_INCOMPATIBLE, coverage, guarantee, (validation_error,))
            )
            continue
        if incident.topology_id != COMMON_TOPOLOGY_ID:
            reason = "incident topology is not the supported synthetic parallel-pump two-tank model"
            coverage = _placeholder_certificate(CertificateStatus.INCOMPATIBLE_CONTEXT, reason, certificate_started)
            preliminary.append(
                (policy, SelectionStatus.INVALID_OR_INCOMPATIBLE, coverage, guarantee, (reason,))
            )
            continue
        context = _project_context(incident, policy)
        coverage = (
            check_controlled_safe_hold_recovery(
                context,
                attacker_schedule=incident.attacker_schedule,
                manifest_path=(
                    certificate_paths.controlled_safe_hold
                    if certificate_paths.controlled_safe_hold is not None
                    else certificate_paths.controlled_hold
                ),
            )
            if policy == CONTROLLED_SAFE_HOLD
            else check_state_dependent_recovery(context, manifest_path=certificate_paths.flowing_takeover)
            if policy == FLOWING_TAKEOVER
            else check_intermediate_delay_recovery(
                context,
                attacker_schedule=incident.attacker_schedule,
                manifest_path=certificate_paths.intermediate_flowing_takeover,
            )
            if policy == INTERMEDIATE_FLOWING_TAKEOVER
            else check_delayed_isolation_recovery(
                context,
                attacker_schedule=incident.attacker_schedule,
                manifest_path=certificate_paths.delayed_flowing_takeover,
            )
        )
        certificate_status = _status_from_certificate(coverage)
        if certificate_status is not None:
            preliminary.append((policy, certificate_status, coverage, guarantee, coverage.reasons))
            continue
        reasons = tuple(_requirement_reasons(guarantee, incident.service))
        status = SelectionStatus.ADMISSIBLE if not reasons else SelectionStatus.COVERED_SERVICE_INADEQUATE
        preliminary.append((policy, status, coverage, guarantee, reasons))
    certificate_latency = (time.perf_counter() - certificate_started) * 1_000

    simulation_started = time.perf_counter()
    candidates: list[PolicySelectionResult] = []
    for policy, status, coverage, guarantee, reasons in preliminary:
        trace: dict[str, object] | None = None
        cost: RecoveryCost | None = None
        if simulate_for_diagnostics and validation_error is None and incident.topology_id == COMMON_TOPOLOGY_ID:
            trace, cost = _trace_and_cost(
                incident,
                policy,
                guarantee,
                include_cost=status is SelectionStatus.ADMISSIBLE,
            )
        candidates.append(
            PolicySelectionResult(
                policy=policy,
                status=status,
                certificate=coverage,
                guarantee=guarantee,
                reasons=reasons,
                trace=trace,
                cost=cost,
                cost_comparable=status is SelectionStatus.ADMISSIBLE and cost is not None,
            )
        )
    simulation_latency = (time.perf_counter() - simulation_started) * 1_000

    admissible = [candidate for candidate in candidates if candidate.admissible]
    costed_admissible = [candidate for candidate in admissible if candidate.cost is not None]
    if costed_admissible:
        selected = min(
            costed_admissible,
            key=lambda candidate: (
                float("inf") if candidate.cost is None else candidate.cost.total,
                candidate.policy,
            ),
        )
        selected_policy = selected.policy
        selection_status = RecoverySelectionStatus.SELECTED
        reason = "selected the lowest simulated trace-derived cost among certificate-covered compatible policies"
    elif admissible:
        selected_policy = None
        selection_status = RecoverySelectionStatus.NO_ADMISSIBLE_CANDIDATE
        reason = "certificate-covered policies meet the request, but trace-derived cost estimation was not run"
    else:
        selected_policy = None
        if validation_error is not None:
            selection_status = RecoverySelectionStatus.INVALID_INCIDENT
            reason = "incident context or service contract is invalid; no certificate or cost decision was made"
        elif template_report.no_supported_template:
            selection_status = RecoverySelectionStatus.NO_SUPPORTED_TEMPLATE
            reason = (
                "no currently supported recovery template matches the incident's explicitly trusted resources; "
                "this does not claim global recovery infeasibility"
            )
        else:
            selection_status = RecoverySelectionStatus.NO_ADMISSIBLE_CANDIDATE
            reason = "no evaluated policy is both certificate-covered and sufficient for the incident contract"
    return RecoverySelection(
        incident=incident,
        template_applicability=template_report,
        candidates=tuple(candidates),
        selected_policy=selected_policy,
        status=selection_status,
        selection_reason=reason,
        certificate_and_admissibility_latency_ms=certificate_latency,
        simulation_and_cost_latency_ms=simulation_latency,
        total_local_latency_ms=(time.perf_counter() - total_started) * 1_000,
    )
