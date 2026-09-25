"""Ground evidence-derived candidates into the existing formal RecoveryContext."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace
from enum import Enum

from .candidate_context import CandidateClaim, CandidateRecoveryContext, CandidateStatus
from .context import RecoveryContext, RecoveryControlPathAuthority, RecoveryResourceAvailability
from .model import AttackerAction, PlantState, TwoTankPlant
from .trusted_plant_knowledge import (
    RecoveryConfiguration,
    TrustedKnowledgeValidationError,
    TrustedPlantKnowledge,
)


class GroundingStatus(str, Enum):
    GROUNDED_CONTEXT = "GROUNDED_CONTEXT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    UNSUPPORTED_COMPONENT = "UNSUPPORTED_COMPONENT"
    UNSUPPORTED_ATTACK_CAPABILITY = "UNSUPPORTED_ATTACK_CAPABILITY"
    UNKNOWN_RESOURCE_STATUS = "UNKNOWN_RESOURCE_STATUS"
    UNTRUSTED_RESOURCE = "UNTRUSTED_RESOURCE"
    MISSING_TIMING_INFORMATION = "MISSING_TIMING_INFORMATION"
    INCOMPATIBLE_PLANT_KNOWLEDGE = "INCOMPATIBLE_PLANT_KNOWLEDGE"
    INVALID_EVIDENCE = "INVALID_EVIDENCE"


@dataclass(frozen=True)
class GroundedFieldProvenance:
    field: str
    value: object
    candidate_status: CandidateStatus | None
    evidence_ids: tuple[str, ...]
    knowledge_ids: tuple[str, ...]
    configuration_ids: tuple[str, ...]
    grounding_notes: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "field": self.field,
            "value": _serialize(self.value),
            "candidate_status": None if self.candidate_status is None else self.candidate_status.value,
            "evidence_ids": list(self.evidence_ids),
            "knowledge_ids": list(self.knowledge_ids),
            "configuration_ids": list(self.configuration_ids),
            "grounding_notes": list(self.grounding_notes),
        }


@dataclass(frozen=True)
class ResourceGrounding:
    resource: str
    control: str
    observed_operational: bool
    physically_present: bool
    trusted_for_incident: bool
    controllable_by_recovery: bool
    available_for_template: bool
    evidence_ids: tuple[str, ...]
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self) | {"evidence_ids": list(self.evidence_ids), "reasons": list(self.reasons)}


@dataclass(frozen=True)
class GroundedRecoveryContext:
    """Associated provenance plus the unchanged downstream formal context."""

    context: RecoveryContext
    candidate: CandidateRecoveryContext
    knowledge_id: str
    recovery_configuration_id: str
    field_provenance: tuple[GroundedFieldProvenance, ...]
    resource_groundings: tuple[ResourceGrounding, ...]
    attacker_schedule: tuple[AttackerAction, ...] | None

    def provenance_for(self, field: str) -> GroundedFieldProvenance:
        return next(item for item in self.field_provenance if item.field == field)

    def as_dict(self) -> dict[str, object]:
        return {
            "context": self.context.as_dict(),
            "candidate": self.candidate.as_dict(),
            "knowledge_id": self.knowledge_id,
            "recovery_configuration_id": self.recovery_configuration_id,
            "field_provenance": [item.as_dict() for item in self.field_provenance],
            "resource_groundings": [item.as_dict() for item in self.resource_groundings],
            "attacker_schedule": None
            if self.attacker_schedule is None
            else [action.value for action in self.attacker_schedule],
        }


@dataclass(frozen=True)
class GroundingResult:
    status: GroundingStatus
    reasons: tuple[str, ...]
    grounded: GroundedRecoveryContext | None

    @property
    def succeeded(self) -> bool:
        return self.status is GroundingStatus.GROUNDED_CONTEXT and self.grounded is not None

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "succeeded": self.succeeded,
            "reasons": list(self.reasons),
            "grounded": None if self.grounded is None else self.grounded.as_dict(),
        }


def _result(status: GroundingStatus, *reasons: str) -> GroundingResult:
    return GroundingResult(status, tuple(reasons), None)


def _claim_failure(claim: CandidateClaim, field: str, *, resource: bool = False) -> GroundingResult | None:
    if claim.status is CandidateStatus.CONFLICTING:
        return _result(GroundingStatus.CONFLICTING_EVIDENCE, f"{field}: {claim.note}")
    if claim.status is CandidateStatus.REJECTED:
        return _result(GroundingStatus.INVALID_EVIDENCE, f"{field}: {claim.note}")
    if claim.status is CandidateStatus.UNKNOWN or claim.value is None:
        status = GroundingStatus.UNKNOWN_RESOURCE_STATUS if resource else GroundingStatus.INSUFFICIENT_EVIDENCE
        return _result(status, f"{field}: {claim.note}")
    return None


def _timing_value(
    candidate: CandidateClaim,
    configured: float | None,
    name: str,
    configuration_id: str,
) -> tuple[float, GroundedFieldProvenance] | GroundingResult:
    if candidate.status is CandidateStatus.CONFLICTING:
        return _result(GroundingStatus.CONFLICTING_EVIDENCE, f"{name}: {candidate.note}")
    if candidate.status is CandidateStatus.REJECTED:
        return _result(GroundingStatus.INVALID_EVIDENCE, f"{name}: {candidate.note}")
    if configured is None and (candidate.status is CandidateStatus.UNKNOWN or candidate.value is None):
        return _result(
            GroundingStatus.MISSING_TIMING_INFORMATION,
            f"{name} is absent from both evidence and recovery configuration",
        )
    try:
        observed = None if candidate.value is None else float(candidate.value)
    except (TypeError, ValueError):
        return _result(GroundingStatus.INVALID_EVIDENCE, f"{name} is not numeric timing evidence")
    if observed is not None and (not math.isfinite(observed) or observed < 0):
        return _result(GroundingStatus.INVALID_EVIDENCE, f"{name} must be finite and nonnegative")
    if configured is not None and observed is not None and not math.isclose(
        configured, observed, rel_tol=0.0, abs_tol=1e-12
    ):
        return _result(
            GroundingStatus.INCOMPATIBLE_PLANT_KNOWLEDGE,
            f"{name} evidence value {observed} conflicts with configured value {configured}; no rounding occurred",
        )
    value = configured if configured is not None else observed
    assert value is not None
    return (
        value,
        GroundedFieldProvenance(
            name,
            value,
            candidate.status,
            candidate.evidence_ids,
            (),
            (configuration_id,),
            (
                "configured timing is authoritative after agreement with any observed timing",
                "observed timing is retained only as provenance when configuration is explicit",
            ),
        ),
    )


def _resource_grounding(
    resource: str,
    control: str,
    claim: CandidateClaim,
    knowledge: TrustedPlantKnowledge,
    configuration: RecoveryConfiguration,
) -> ResourceGrounding | GroundingResult:
    failure = _claim_failure(claim, f"{resource} operational status", resource=True)
    if failure:
        return failure
    observed = bool(claim.value)
    physical = resource in knowledge.component_ids() and control in knowledge.context_components()
    trusted = control in configuration.trusted_controls
    controllable = control in configuration.controllable_controls
    reasons = []
    if not physical:
        reasons.append("trusted plant knowledge does not contain this component/control mapping")
    if not observed:
        reasons.append("evidence reports the resource as unavailable")
    if not trusted:
        reasons.append("recovery configuration does not trust this control for this incident")
    if not controllable:
        reasons.append("recovery configuration does not authorize recovery-layer control")
    return ResourceGrounding(
        resource,
        control,
        observed,
        physical,
        trusted,
        controllable,
        physical and observed and trusted and controllable,
        claim.evidence_ids,
        tuple(reasons),
    )


def ground_candidate_context(
    candidate: CandidateRecoveryContext,
    trusted_plant_knowledge: TrustedPlantKnowledge,
    recovery_configuration: RecoveryConfiguration,
) -> GroundingResult:
    """Validate and convert candidate claims without adding missing incident facts.

    A known-but-untrusted or unavailable resource produces a grounded context
    with that recovery path marked false. It is not silently promoted to a
    trusted path, and it still permits a different supported template to apply.
    """

    try:
        trusted_plant_knowledge.validate()
        recovery_configuration.validate()
    except TrustedKnowledgeValidationError as exc:
        return _result(GroundingStatus.INCOMPATIBLE_PLANT_KNOWLEDGE, str(exc))

    plant_claim_failure = _claim_failure(candidate.plant_identity, "plant identity")
    if plant_claim_failure:
        return plant_claim_failure
    if candidate.plant_identity.value != trusted_plant_knowledge.plant_identity:
        return _result(
            GroundingStatus.INCOMPATIBLE_PLANT_KNOWLEDGE,
            "incident evidence plant identity does not match trusted plant knowledge",
        )

    for name, claim in (
        ("x1", candidate.x1),
        ("x2", candidate.x2),
        ("P1 command", candidate.p1_command),
        ("suspected compromised component", candidate.suspected_compromised_component),
        ("attacker capability", candidate.attacker_capability),
    ):
        failure = _claim_failure(claim, name)
        if failure:
            return failure

    if not candidate.x1.evidence_ids or not candidate.x2.evidence_ids:
        return _result(
            GroundingStatus.INVALID_EVIDENCE,
            "tank-state claims require explicit evidence provenance",
        )
    if not candidate.x1.sources or not candidate.x2.sources:
        return _result(
            GroundingStatus.INVALID_EVIDENCE,
            "tank-state claims require explicit observation-source provenance",
        )
    if not set(candidate.x1.sources + candidate.x2.sources) <= trusted_plant_knowledge.trusted_observation_sources:
        return _result(
            GroundingStatus.INVALID_EVIDENCE,
            "tank-state observation source is not trusted by the configured plant knowledge",
        )
    if (
        trusted_plant_knowledge.observation_target("x1") != "x1"
        or trusted_plant_knowledge.observation_target("x2") != "x2"
    ):
        return _result(
            GroundingStatus.INCOMPATIBLE_PLANT_KNOWLEDGE,
            "trusted plant knowledge does not map x1 and x2 observations to the formal tank state",
        )
    if candidate.suspected_compromised_component.value != "P1":
        return _result(
            GroundingStatus.UNSUPPORTED_COMPONENT,
            "candidate compromise is not the one modeled P1 command surface",
        )
    attacker_actions = trusted_plant_knowledge.attack_actions(str(candidate.attacker_capability.value))
    if attacker_actions is None:
        return _result(
            GroundingStatus.UNSUPPORTED_ATTACK_CAPABILITY,
            "candidate attacker capability has no declared mapping to the formal attacker alphabet",
        )

    timings: dict[str, float] = {}
    timing_provenance: list[GroundedFieldProvenance] = []
    for name, claim, configured in (
        ("control_period", candidate.control_period, recovery_configuration.control_period),
        ("isolation_delay", candidate.isolation_delay, recovery_configuration.isolation_delay),
        ("backup_startup_delay", candidate.backup_startup_delay, recovery_configuration.backup_startup_delay),
        (
            "transfer_recovery_deadline",
            CandidateClaim.unknown("transfer deadline is recovery configuration only"),
            recovery_configuration.transfer_recovery_deadline,
        ),
        ("horizon", CandidateClaim.unknown("horizon is recovery configuration only"), recovery_configuration.horizon),
    ):
        resolved = _timing_value(claim, configured, name, recovery_configuration.configuration_id)
        if isinstance(resolved, GroundingResult):
            return resolved
        timings[name], provenance = resolved
        timing_provenance.append(provenance)

    resources: list[ResourceGrounding] = []
    for resource, control, claim in (
        ("P2", "P2_command", candidate.backup_operational),
        ("isolator", "primary_isolator", candidate.isolation_operational),
        ("upstream_gate", "upstream_gate", candidate.inflow_control_operational),
        ("demand_gate", "demand_gate", candidate.demand_control_operational),
    ):
        grounded_resource = _resource_grounding(
            resource, control, claim, trusted_plant_knowledge, recovery_configuration
        )
        if isinstance(grounded_resource, GroundingResult):
            return grounded_resource
        resources.append(grounded_resource)
    resource_by_name = {resource.resource: resource for resource in resources}
    if not trusted_plant_knowledge.is_backup_for("P1", "P2"):
        return _result(
            GroundingStatus.INCOMPATIBLE_PLANT_KNOWLEDGE,
            "trusted knowledge does not explicitly relate P2 as backup for P1",
        )

    schedule: tuple[AttackerAction, ...] | None
    schedule_claim = candidate.attacker_command_schedule
    if schedule_claim.status is CandidateStatus.CONFLICTING:
        return _result(GroundingStatus.CONFLICTING_EVIDENCE, f"attacker command schedule: {schedule_claim.note}")
    if schedule_claim.status is CandidateStatus.REJECTED:
        return _result(GroundingStatus.UNSUPPORTED_ATTACK_CAPABILITY, schedule_claim.note)
    if schedule_claim.status is CandidateStatus.UNKNOWN:
        schedule = None
    elif isinstance(schedule_claim.value, tuple) and all(
        isinstance(action, AttackerAction) for action in schedule_claim.value
    ):
        schedule = schedule_claim.value
    else:
        return _result(
            GroundingStatus.UNSUPPORTED_ATTACK_CAPABILITY,
            "candidate command schedule is not in the formal P1 action alphabet",
        )

    plant = replace(
        trusted_plant_knowledge.plant_parameters,
        control_period=timings["control_period"],
        isolation_delay=timings["isolation_delay"],
        backup_startup_delay=timings["backup_startup_delay"],
        transfer_recovery_deadline=timings["transfer_recovery_deadline"],
        horizon=timings["horizon"],
    )
    if type(candidate.p1_command.value) is not bool:
        return _result(GroundingStatus.INVALID_EVIDENCE, "P1 command must be a boolean state")
    try:
        state = PlantState(
            x1=float(candidate.x1.value),
            x2=float(candidate.x2.value),
            p1_command=bool(candidate.p1_command.value),
            p2_command=False,
            upstream_enabled=True,
            demand_enabled=True,
        )
        base = RecoveryContext.from_plant(TwoTankPlant(plant, state))
    except ValueError as exc:
        return _result(GroundingStatus.INVALID_EVIDENCE, f"state or timing is outside the formal plant domain: {exc}")

    availability = RecoveryResourceAvailability(
        trusted_isolation_available=resource_by_name["isolator"].available_for_template,
        trusted_backup_available=resource_by_name["P2"].available_for_template,
        trusted_inflow_control_available=resource_by_name["upstream_gate"].available_for_template,
        trusted_demand_control_available=resource_by_name["demand_gate"].available_for_template,
    )
    operational_controls = frozenset(
        item.control for item in resources if item.observed_operational
    )
    context = replace(
        base,
        compromised_components=frozenset({"P1_command_path"}),
        attacker_capabilities=frozenset(attacker_actions),
        trusted_actuators=frozenset(recovery_configuration.trusted_controls),
        control_path_authority=RecoveryControlPathAuthority(
            operational=operational_controls,
            trusted=recovery_configuration.trusted_controls,
            controllable_by_recovery=recovery_configuration.controllable_controls,
        ),
        resource_availability=availability,
        available_recovery_resources={
            "backup_capacity": plant.backup_capacity,
            "primary_isolation": "isolator" in trusted_plant_knowledge.component_ids(),
        },
        process_dependencies=trusted_plant_knowledge.process_dependency_mapping(),
        takeover_assurance=recovery_configuration.assurance,
        plant_model_id=trusted_plant_knowledge.formal_plant_model_id,
        recovery_policy_id=trusted_plant_knowledge.default_recovery_policy_id,
    )
    try:
        context.validate()
    except ValueError as exc:
        return _result(GroundingStatus.INCOMPATIBLE_PLANT_KNOWLEDGE, str(exc))

    provenance = [
        GroundedFieldProvenance(
            "plant_identity",
            trusted_plant_knowledge.plant_identity,
            candidate.plant_identity.status,
            candidate.plant_identity.evidence_ids,
            (trusted_plant_knowledge.knowledge_id,),
            (),
            ("evidence identity matches trusted plant identity",),
        ),
        GroundedFieldProvenance(
            "compromised_component",
            "P1_command_path",
            candidate.suspected_compromised_component.status,
            candidate.suspected_compromised_component.evidence_ids,
            (trusted_plant_knowledge.knowledge_id,),
            (),
            ("candidate P1 maps to the formal P1_command_path control surface",),
        ),
        GroundedFieldProvenance(
            "attacker_capabilities",
            tuple(action.value for action in attacker_actions),
            candidate.attacker_capability.status,
            candidate.attacker_capability.evidence_ids,
            (trusted_plant_knowledge.knowledge_id,),
            (),
            ("only a declared formal attacker capability mapping is accepted",),
        ),
        GroundedFieldProvenance(
            "x1",
            context.current_state.x1,
            candidate.x1.status,
            candidate.x1.evidence_ids,
            (trusted_plant_knowledge.knowledge_id,),
            (),
            ("trusted observation source and signal are grounded to T1 state",),
        ),
        GroundedFieldProvenance(
            "x2",
            context.current_state.x2,
            candidate.x2.status,
            candidate.x2.evidence_ids,
            (trusted_plant_knowledge.knowledge_id,),
            (),
            ("trusted observation source and signal are grounded to T2 state",),
        ),
        GroundedFieldProvenance(
            "formal_initial_control_state",
            {"p2_command": False, "upstream_enabled": True, "demand_enabled": True},
            None,
            (),
            (trusted_plant_knowledge.knowledge_id,),
            (recovery_configuration.configuration_id,),
            ("pre-recovery control state is an explicit synthetic formal-model initialization, not inferred telemetry",),
        ),
        *timing_provenance,
    ]
    for resource in resources:
        claim = {
            "P2": candidate.backup_operational,
            "isolator": candidate.isolation_operational,
            "upstream_gate": candidate.inflow_control_operational,
            "demand_gate": candidate.demand_control_operational,
        }[resource.resource]
        provenance.append(
            GroundedFieldProvenance(
                f"resource:{resource.resource}",
                resource.available_for_template,
                claim.status,
                claim.evidence_ids,
                (trusted_plant_knowledge.knowledge_id,),
                (recovery_configuration.configuration_id,),
                resource.reasons
                or ("observed operational resource is physically present, trusted, and recovery-controllable",),
            )
        )
    return GroundingResult(
        GroundingStatus.GROUNDED_CONTEXT,
        (
            "candidate evidence was grounded against the fixed synthetic topology and explicit recovery configuration",
            "resource observations remain separate from trust and recovery-authority decisions",
        ),
        GroundedRecoveryContext(
            context,
            candidate,
            trusted_plant_knowledge.knowledge_id,
            recovery_configuration.configuration_id,
            tuple(provenance),
            tuple(resources),
            schedule,
        ),
    )


def _serialize(value: object) -> object:
    if isinstance(value, AttackerAction):
        return value.value
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value
