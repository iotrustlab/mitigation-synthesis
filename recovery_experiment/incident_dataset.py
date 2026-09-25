"""Fixed synthetic evidence cases and independently declared gold labels.

The labels in this file come from ``IncidentScenarioSpec`` values, not from
``DeterministicIncidentInterpreter`` or ``ground_candidate_context``.  This
makes the dataset suitable for evaluating a future interpreter against the
same candidate and grounded-context schema.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .candidate_context import CandidateClaim, CandidateRecoveryContext, CandidateStatus
from .context import RecoveryContext, RecoveryControlPathAuthority, RecoveryResourceAvailability
from .context_grounding import (
    GroundedFieldProvenance,
    GroundedRecoveryContext,
    GroundingStatus,
    ResourceGrounding,
)
from .incident_evidence import (
    Alert,
    CommandEvent,
    EvidenceQuality,
    IncidentEvidence,
    Observation,
    ResourceObservation,
    ResourceStatus,
)
from .model import AttackerAction, PlantParameters, PlantState
from .scenarios import context_for
from .trusted_plant_knowledge import (
    RecoveryConfiguration,
    TrustedPlantKnowledge,
    synthetic_recovery_configuration,
    synthetic_two_tank_knowledge,
)


DATASET_SEED = 20260924
FLOWING_TEMPLATE = "flowing_backup_takeover"
SAFE_HOLD_TEMPLATE = "controlled_safe_hold"
FLOWING_MODEL = "state-dependent-flowing-takeover-v1"
SAFE_HOLD_MODEL = "controlled-safe-hold-immediate-isolation-v1"
INTERMEDIATE_MODEL = "built-one-control-period-isolation-flowing-takeover-v1"
DELAYED_MODEL = "delayed-isolation-flowing-takeover-v1"


@dataclass(frozen=True)
class GoldIncidentLabels:
    """Scenario-spec labels; they are never computed from pipeline output."""

    grounding_status: GroundingStatus
    candidate_values: tuple[tuple[str, object | None], ...]
    applicable_templates: tuple[str, ...]
    formal_models: tuple[tuple[str, str | None], ...]
    certificate_statuses: tuple[tuple[str, str | None], ...]
    selection_status: str | None
    selected_policy: str | None
    service_statuses: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "grounding_status": self.grounding_status.value,
            "candidate_values": dict(self.candidate_values),
            "applicable_templates": list(self.applicable_templates),
            "formal_models": dict(self.formal_models),
            "certificate_statuses": dict(self.certificate_statuses),
            "selection_status": self.selection_status,
            "selected_policy": self.selected_policy,
            "service_statuses": dict(self.service_statuses),
        }


@dataclass(frozen=True)
class SyntheticIncidentCase:
    scenario_id: str
    family: str
    evidence: IncidentEvidence
    ground_truth_candidate: CandidateRecoveryContext
    ground_truth_context: GroundedRecoveryContext | None
    trusted_plant_knowledge: TrustedPlantKnowledge
    recovery_configuration: RecoveryConfiguration
    gold: GoldIncidentLabels


@dataclass(frozen=True)
class SyntheticIncidentDataset:
    seed: int
    cases: tuple[SyntheticIncidentCase, ...]


@dataclass(frozen=True)
class IncidentScenarioSpec:
    """Declarative ground truth for one deterministic synthetic incident."""

    scenario_id: str
    family: str
    x1: float = 7.0
    x2: float = 6.0
    control_period: float = 0.5
    isolation_delay: float = 0.0
    backup_startup_delay: float = 1.0
    p2_operational: bool = True
    isolator_operational: bool = True
    inflow_operational: bool = True
    demand_operational: bool = True
    trusted_controls: frozenset[str] = frozenset(
        {"primary_isolator", "P2_command", "upstream_gate", "demand_gate"}
    )
    controllable_controls: frozenset[str] = frozenset(
        {"primary_isolator", "P2_command", "upstream_gate", "demand_gate"}
    )
    required_delivered_flow: float = 1.2
    require_continuous_delivery: bool = True
    permitted_interruption_duration: float = 0.0
    missing_fields: frozenset[str] = frozenset()
    conflicting_resource: str | None = None
    unsupported_command: str | None = None


def build_synthetic_incident_dataset(seed: int = DATASET_SEED) -> SyntheticIncidentDataset:
    """Return the fixed-seed 27-case evaluation suite.

    The suite intentionally covers A--K from the incident-evidence contract.
    Its order and raw evidence identifiers are stable for reproducible reports.
    """

    if seed != DATASET_SEED:
        raise ValueError(f"this reference dataset is fixed at seed {DATASET_SEED}")
    return SyntheticIncidentDataset(seed, tuple(_case_from_spec(spec) for spec in _scenario_specs()))


def _scenario_specs() -> tuple[IncidentScenarioSpec, ...]:
    relaxed = {
        "required_delivered_flow": 0.0,
        "require_continuous_delivery": False,
        "permitted_interruption_duration": 6.0,
    }
    full = frozenset({"primary_isolator", "P2_command", "upstream_gate", "demand_gate"})
    return (
        # A. Immediate isolation with a healthy trusted backup.
        IncidentScenarioSpec("A-immediate-nominal-1", "A"),
        IncidentScenarioSpec("A-immediate-nominal-2", "A", x1=7.5, x2=6.5),
        IncidentScenarioSpec("A-immediate-nominal-3", "A", x1=8.0, x2=6.2),
        # B. Two reviewed delayed schedules: 1T/3T and 2T/3T.
        IncidentScenarioSpec("B-1T3T-1", "B", isolation_delay=0.5, backup_startup_delay=1.5),
        IncidentScenarioSpec("B-1T3T-2", "B", x1=7.5, x2=6.5, isolation_delay=0.5, backup_startup_delay=1.5),
        IncidentScenarioSpec("B-1T3T-3", "B", x1=8.0, x2=6.2, isolation_delay=0.5, backup_startup_delay=1.5),
        IncidentScenarioSpec("B-2T3T-1", "B", isolation_delay=1.0, backup_startup_delay=1.5),
        IncidentScenarioSpec("B-2T3T-2", "B", x1=7.5, x2=6.5, isolation_delay=1.0, backup_startup_delay=1.5),
        IncidentScenarioSpec("B-2T3T-3", "B", x1=8.0, x2=6.2, isolation_delay=1.0, backup_startup_delay=1.5),
        # C. P2 is observed unavailable, but independent hold resources work.
        IncidentScenarioSpec("C-p2-unavailable-1", "C", p2_operational=False, **relaxed),
        IncidentScenarioSpec("C-p2-unavailable-2", "C", x1=8.0, x2=5.0, p2_operational=False, **relaxed),
        # D. P2 is observed healthy but recovery is not authorized to trust it.
        IncidentScenarioSpec("D-p2-untrusted-1", "D", trusted_controls=full - {"P2_command"}, **relaxed),
        IncidentScenarioSpec("D-p2-untrusted-2", "D", x1=8.0, x2=5.0, trusted_controls=full - {"P2_command"}, **relaxed),
        # E. Hold gates are unavailable; flowing takeover remains possible.
        IncidentScenarioSpec("E-hold-controls-unavailable-1", "E", inflow_operational=False),
        IncidentScenarioSpec("E-hold-controls-unavailable-2", "E", demand_operational=False),
        # F. Isolation is observed unavailable; this catalogue has no template.
        IncidentScenarioSpec("F-isolation-unavailable-1", "F", isolator_operational=False),
        IncidentScenarioSpec("F-isolation-unavailable-2", "F", trusted_controls=full - {"primary_isolator"}),
        # G. Valid plant state outside flowing-certificate margins; hold is admissible.
        IncidentScenarioSpec("G-margin-outside-1", "G", x1=4.0, x2=3.0, **relaxed),
        IncidentScenarioSpec("G-margin-outside-2", "G", x1=4.2, x2=3.1, **relaxed),
        # H. The safety hold cannot satisfy a continuous positive-service request.
        IncidentScenarioSpec("H-continuous-service-1", "H", p2_operational=False),
        IncidentScenarioSpec("H-continuous-service-2", "H", x1=8.0, x2=5.0, p2_operational=False),
        # I. 0.75 s is deliberately not rounded to an integer control schedule.
        IncidentScenarioSpec("I-unsupported-timing-1", "I", isolation_delay=0.75, backup_startup_delay=1.5),
        IncidentScenarioSpec("I-unsupported-timing-2", "I", x1=7.5, x2=6.5, isolation_delay=0.75, backup_startup_delay=1.5),
        # J. Same-timestamp P2 evidence is irreconcilable under the documented rule.
        IncidentScenarioSpec("J-conflicting-p2", "J", conflicting_resource="P2"),
        # K. Distinguish missing state, timing, and resource observations.
        IncidentScenarioSpec("K-missing-x2", "K", missing_fields=frozenset({"x2"})),
        IncidentScenarioSpec("K-missing-isolation-timing", "K", missing_fields=frozenset({"isolation_delay"})),
        IncidentScenarioSpec("K-missing-p2-health", "K", missing_fields=frozenset({"P2"})),
    )


def _case_from_spec(spec: IncidentScenarioSpec) -> SyntheticIncidentCase:
    parameters = replace(
        PlantParameters(),
        control_period=spec.control_period,
        isolation_delay=spec.isolation_delay,
        backup_startup_delay=spec.backup_startup_delay,
    )
    knowledge = synthetic_two_tank_knowledge(parameters)
    configuration = replace(
        synthetic_recovery_configuration(parameters),
        trusted_controls=spec.trusted_controls,
        controllable_controls=spec.controllable_controls,
        required_delivered_flow=spec.required_delivered_flow,
        require_continuous_delivery=spec.require_continuous_delivery,
        permitted_interruption_duration=spec.permitted_interruption_duration,
        isolation_delay=(None if "isolation_delay" in spec.missing_fields else spec.isolation_delay),
    )
    configuration.validate()
    evidence = _evidence_from_spec(spec, knowledge.plant_identity)
    candidate = _candidate_from_spec(spec, knowledge.plant_identity)
    status = _expected_grounding_status(spec)
    grounded = _ground_truth_context(spec, candidate, knowledge, configuration) if status is GroundingStatus.GROUNDED_CONTEXT else None
    return SyntheticIncidentCase(
        spec.scenario_id,
        spec.family,
        evidence,
        candidate,
        grounded,
        knowledge,
        configuration,
        _gold_from_spec(spec),
    )


def _evidence_from_spec(spec: IncidentScenarioSpec, plant_identity: str) -> IncidentEvidence:
    observations = [
        _observation(spec, "x1", spec.x1),
        _observation(spec, "P1_command", "OFF"),
        _observation(spec, "control_period", spec.control_period),
        _observation(spec, "backup_startup_delay", spec.backup_startup_delay),
    ]
    if "x2" not in spec.missing_fields:
        observations.append(_observation(spec, "x2", spec.x2))
    if "isolation_delay" not in spec.missing_fields:
        observations.append(_observation(spec, "isolation_delay", spec.isolation_delay))
    resources = []
    resource_values = {
        "P2": spec.p2_operational,
        "isolator": spec.isolator_operational,
        "upstream_gate": spec.inflow_operational,
        "demand_gate": spec.demand_operational,
    }
    for resource, available in resource_values.items():
        if resource not in spec.missing_fields:
            resources.append(_resource(spec, resource, available, f"resource:{resource}:latest"))
    if spec.conflicting_resource is not None:
        resources.append(_resource(spec, spec.conflicting_resource, False, f"resource:{spec.conflicting_resource}:conflict"))
    command = spec.unsupported_command or "OFF"
    command_events = tuple(
        CommandEvent(
            0.5 + index * 0.1,
            "P1",
            command,
            "synthetic_ids",
            False,
            f"{spec.scenario_id}:command:p1:{index}",
        )
        for index in range(_schedule_count(spec))
    )
    return IncidentEvidence(
        scenario_id=spec.scenario_id,
        window_start=0.0,
        window_end=1.0,
        observations=tuple(observations),
        alerts=(Alert(0.25, "unauthorized_p1_command", "P1", "high", 1.0, f"{spec.scenario_id}:alert:p1"),),
        command_events=command_events,
        resource_observations=tuple(resources),
        metadata={"plant_identity": plant_identity, "dataset_seed": str(DATASET_SEED)},
    )


def _schedule_count(spec: IncidentScenarioSpec) -> int:
    """The raw trace explicitly carries each modeled delayed attacker period."""

    if spec.control_period > 0 and spec.isolation_delay > 0:
        periods = spec.isolation_delay / spec.control_period
        if periods.is_integer() and periods >= 1:
            return int(periods)
    return 1


def _observation(spec: IncidentScenarioSpec, signal: str, value: object) -> Observation:
    return Observation(
        1.0,
        "synthetic_telemetry",
        signal,
        value,  # type: ignore[arg-type]  # The factory only supplies JSON scalars.
        "synthetic" if signal in {"x1", "x2"} else None,
        EvidenceQuality.GOOD,
        f"{spec.scenario_id}:observation:{signal}",
    )


def _resource(spec: IncidentScenarioSpec, resource: str, available: bool, provenance_id: str) -> ResourceObservation:
    return ResourceObservation(
        1.0,
        resource,
        ResourceStatus.AVAILABLE if available else ResourceStatus.UNAVAILABLE,
        "synthetic_telemetry",
        1.0,
        f"{spec.scenario_id}:{provenance_id}",
    )


def _candidate_from_spec(spec: IncidentScenarioSpec, plant_identity: str) -> CandidateRecoveryContext:
    def observed(value: object, name: str) -> CandidateClaim:
        return CandidateClaim(
            value,
            CandidateStatus.OBSERVED,
            evidence_ids=(f"{spec.scenario_id}:observation:{name}",),
            sources=("synthetic_telemetry",),
            note="scenario-spec gold candidate observation",
        )

    def resource(value: bool, name: str) -> CandidateClaim:
        if name in spec.missing_fields:
            return CandidateClaim.unknown(f"scenario specification intentionally omits {name} evidence")
        if name == spec.conflicting_resource:
            return CandidateClaim.conflicting(
                (f"{spec.scenario_id}:resource:{name}:latest", f"{spec.scenario_id}:resource:{name}:conflict"),
                "scenario specification declares same-timestamp conflicting resource evidence",
            )
        return CandidateClaim(
            value,
            CandidateStatus.OBSERVED,
            evidence_ids=(f"{spec.scenario_id}:resource:{name}:latest",),
            sources=("synthetic_telemetry",),
            note="scenario-spec gold resource observation",
        )

    schedule = (
        CandidateClaim(
            tuple(AttackerAction.FORCE_PRIMARY_OFF for _ in range(_schedule_count(spec))),
            CandidateStatus.DERIVED,
            evidence_ids=tuple(
                f"{spec.scenario_id}:command:p1:{index}" for index in range(_schedule_count(spec))
            ),
            sources=("synthetic_ids",),
            rule_ids=("command_schedule",),
            note="scenario-spec formal P1 schedule",
        )
        if spec.unsupported_command is None
        else CandidateClaim(None, CandidateStatus.REJECTED, note="scenario-spec unsupported P1 command")
    )
    return CandidateRecoveryContext(
        incident_id=spec.scenario_id,
        plant_identity=CandidateClaim(
            plant_identity,
            CandidateStatus.OBSERVED,
            evidence_ids=("metadata:plant_identity",),
            sources=("incident_metadata",),
        ),
        suspected_compromised_component=CandidateClaim(
            "P1",
            CandidateStatus.DERIVED,
            evidence_ids=(f"{spec.scenario_id}:alert:p1", f"{spec.scenario_id}:command:p1:0"),
            sources=("synthetic_ids",),
            rule_ids=("p1_compromise",),
        ),
        attacker_capability=CandidateClaim(
            "modify_primary_pump_command",
            CandidateStatus.DERIVED,
            evidence_ids=(f"{spec.scenario_id}:alert:p1", f"{spec.scenario_id}:command:p1:0"),
            sources=("synthetic_ids",),
            rule_ids=("primary_capability",),
        ),
        x1=observed(spec.x1, "x1"),
        x2=(CandidateClaim.unknown("scenario specification intentionally omits x2 evidence") if "x2" in spec.missing_fields else observed(spec.x2, "x2")),
        p1_command=observed(False, "P1_command"),
        p1_actual_state=CandidateClaim.unknown("no P1 actual-state telemetry is required by this formal boundary"),
        backup_operational=resource(spec.p2_operational, "P2"),
        isolation_operational=resource(spec.isolator_operational, "isolator"),
        inflow_control_operational=resource(spec.inflow_operational, "upstream_gate"),
        demand_control_operational=resource(spec.demand_operational, "demand_gate"),
        control_period=observed(spec.control_period, "control_period"),
        isolation_delay=(CandidateClaim.unknown("scenario specification omits isolation timing") if "isolation_delay" in spec.missing_fields else observed(spec.isolation_delay, "isolation_delay")),
        backup_startup_delay=observed(spec.backup_startup_delay, "backup_startup_delay"),
        attacker_command_schedule=schedule,
        relevant_alerts=CandidateClaim(
            (f"{spec.scenario_id}:alert:p1",),
            CandidateStatus.OBSERVED,
            evidence_ids=(f"{spec.scenario_id}:alert:p1",),
            sources=("synthetic_ids",),
        ),
    )


def _expected_grounding_status(spec: IncidentScenarioSpec) -> GroundingStatus:
    if spec.conflicting_resource is not None:
        return GroundingStatus.CONFLICTING_EVIDENCE
    if "isolation_delay" in spec.missing_fields:
        return GroundingStatus.MISSING_TIMING_INFORMATION
    if "P2" in spec.missing_fields:
        return GroundingStatus.UNKNOWN_RESOURCE_STATUS
    if "x2" in spec.missing_fields:
        return GroundingStatus.INSUFFICIENT_EVIDENCE
    return GroundingStatus.GROUNDED_CONTEXT


def _ground_truth_context(
    spec: IncidentScenarioSpec,
    candidate: CandidateRecoveryContext,
    knowledge: TrustedPlantKnowledge,
    configuration: RecoveryConfiguration,
) -> GroundedRecoveryContext:
    """Construct the declared reference context without invoking the grounder."""

    state = PlantState(x1=spec.x1, x2=spec.x2, p1_command=False)
    # Reuse the existing scenario-context constructor without using the new
    # interpreter or grounding layer to derive gold labels.
    base = context_for(knowledge.plant_parameters, state)
    control_values = {
        "P2_command": spec.p2_operational,
        "primary_isolator": spec.isolator_operational,
        "upstream_gate": spec.inflow_operational,
        "demand_gate": spec.demand_operational,
    }
    available = {
        control: operational and control in configuration.trusted_controls and control in configuration.controllable_controls
        for control, operational in control_values.items()
    }
    context = replace(
        base,
        trusted_actuators=configuration.trusted_controls,
        control_path_authority=RecoveryControlPathAuthority(
            operational=frozenset(control for control, operational in control_values.items() if operational),
            trusted=configuration.trusted_controls,
            controllable_by_recovery=configuration.controllable_controls,
        ),
        resource_availability=RecoveryResourceAvailability(
            trusted_isolation_available=available["primary_isolator"],
            trusted_backup_available=available["P2_command"],
            trusted_inflow_control_available=available["upstream_gate"],
            trusted_demand_control_available=available["demand_gate"],
        ),
        process_dependencies=knowledge.process_dependency_mapping(),
        plant_model_id=knowledge.formal_plant_model_id,
        recovery_policy_id=knowledge.default_recovery_policy_id,
    )
    context.validate()
    resources = tuple(
        ResourceGrounding(
            resource={
                "P2_command": "P2",
                "primary_isolator": "isolator",
                "upstream_gate": "upstream_gate",
                "demand_gate": "demand_gate",
            }[control],
            control=control,
            observed_operational=operational,
            physically_present=True,
            trusted_for_incident=control in configuration.trusted_controls,
            controllable_by_recovery=control in configuration.controllable_controls,
            available_for_template=available[control],
            evidence_ids=(),
            reasons=("declared scenario-spec reference grounding",),
        )
        for control, operational in control_values.items()
    )
    provenance = tuple(
        GroundedFieldProvenance(
            field,
            value,
            CandidateStatus.GROUNDED,
            (),
            (knowledge.knowledge_id,),
            (configuration.configuration_id,),
            ("declared scenario-spec gold value",),
        )
        for field, value in (("x1", spec.x1), ("x2", spec.x2), ("isolation_delay", spec.isolation_delay))
    )
    return GroundedRecoveryContext(
        context,
        candidate,
        knowledge.knowledge_id,
        configuration.configuration_id,
        provenance,
        resources,
        tuple(AttackerAction.FORCE_PRIMARY_OFF for _ in range(_schedule_count(spec))),
    )


def _gold_from_spec(spec: IncidentScenarioSpec) -> GoldIncidentLabels:
    status = _expected_grounding_status(spec)
    candidate_values = (
        ("suspected_compromised_component", "P1"),
        ("attacker_capability", "modify_primary_pump_command"),
        ("x1", spec.x1),
        ("x2", None if "x2" in spec.missing_fields else spec.x2),
        ("backup_operational", None if "P2" in spec.missing_fields or spec.conflicting_resource == "P2" else spec.p2_operational),
        (
            "backup_trusted",
            "P2_command" in spec.trusted_controls and "P2_command" in spec.controllable_controls,
        ),
        ("isolation_operational", spec.isolator_operational),
        (
            "isolation_available",
            spec.isolator_operational
            and "primary_isolator" in spec.trusted_controls
            and "primary_isolator" in spec.controllable_controls,
        ),
        ("isolation_delay", None if "isolation_delay" in spec.missing_fields else spec.isolation_delay),
        (
            "hold_controls_available",
            spec.inflow_operational
            and spec.demand_operational
            and "upstream_gate" in spec.trusted_controls
            and "demand_gate" in spec.trusted_controls
            and "upstream_gate" in spec.controllable_controls
            and "demand_gate" in spec.controllable_controls,
        ),
    )
    if status is not GroundingStatus.GROUNDED_CONTEXT:
        return GoldIncidentLabels(status, candidate_values, (), (), (), None, None, ())

    isolation_available = (
        spec.isolator_operational
        and "primary_isolator" in spec.trusted_controls
        and "primary_isolator" in spec.controllable_controls
    )
    p2_available = (
        spec.p2_operational
        and "P2_command" in spec.trusted_controls
        and "P2_command" in spec.controllable_controls
    )
    hold_available = (
        isolation_available
        and spec.inflow_operational
        and spec.demand_operational
        and "upstream_gate" in spec.trusted_controls
        and "demand_gate" in spec.trusted_controls
        and "upstream_gate" in spec.controllable_controls
        and "demand_gate" in spec.controllable_controls
        and spec.isolation_delay == 0.0
    )
    flow_available = isolation_available and p2_available
    templates = tuple(template for template, enabled in ((FLOWING_TEMPLATE, flow_available), (SAFE_HOLD_TEMPLATE, hold_available)) if enabled)
    formal: list[tuple[str, str | None]] = []
    certificates: list[tuple[str, str | None]] = []
    service: list[tuple[str, str]] = []
    if flow_available:
        if spec.isolation_delay == 0.0:
            model = FLOWING_MODEL
            certificate = "NOT_COVERED_BY_CERTIFICATE" if spec.family == "G" else "COVERED_BY_CERTIFICATE"
        elif spec.isolation_delay == 0.5 and spec.backup_startup_delay == 1.5:
            model = INTERMEDIATE_MODEL
            certificate = "COVERED_BY_CERTIFICATE"
        elif spec.isolation_delay == 1.0 and spec.backup_startup_delay == 1.5:
            model = DELAYED_MODEL
            certificate = "COVERED_BY_CERTIFICATE"
        else:
            model = None
            certificate = None
        formal.append((FLOWING_TEMPLATE, model))
        certificates.append((FLOWING_TEMPLATE, certificate))
        flow_policy = (
            FLOWING_TEMPLATE
            if spec.isolation_delay == 0.0
            else "one_control_period_isolation_flowing_backup_takeover"
            if spec.isolation_delay == 0.5
            else "delayed_isolation_flowing_backup_takeover"
        )
        if certificate == "COVERED_BY_CERTIFICATE":
            service.append((flow_policy, "COVERED_AND_REQUIREMENTS_SATISFIED"))
        elif certificate == "NOT_COVERED_BY_CERTIFICATE":
            service.append((flow_policy, "NOT_COVERED_BY_CERTIFICATE"))
    if hold_available:
        formal.append((SAFE_HOLD_TEMPLATE, SAFE_HOLD_MODEL))
        certificates.append((SAFE_HOLD_TEMPLATE, "COVERED_BY_CERTIFICATE"))
        hold_status = (
            "COVERED_BUT_REQUESTED_SERVICE_NOT_ESTABLISHED"
            if spec.require_continuous_delivery and spec.required_delivered_flow > 0
            else "COVERED_AND_REQUIREMENTS_SATISFIED"
        )
        service.append((SAFE_HOLD_TEMPLATE, hold_status))

    selected_policy: str | None = None
    if flow_available and any(item == (FLOWING_TEMPLATE, "COVERED_BY_CERTIFICATE") for item in certificates):
        selected_policy = (
            FLOWING_TEMPLATE
            if spec.isolation_delay == 0.0
            else "one_control_period_isolation_flowing_backup_takeover"
            if spec.isolation_delay == 0.5
            else "delayed_isolation_flowing_backup_takeover"
        )
    if hold_available and not spec.require_continuous_delivery:
        selected_policy = SAFE_HOLD_TEMPLATE
    if not templates:
        selection_status = "NO_SUPPORTED_RECOVERY_TEMPLATE"
    elif selected_policy is not None:
        selection_status = "RECOVERY_TEMPLATE_SELECTED"
    else:
        selection_status = "NO_FORMALLY_ADMISSIBLE_CANDIDATE"
    return GoldIncidentLabels(
        status,
        candidate_values,
        templates,
        tuple(formal),
        tuple(certificates),
        selection_status,
        selected_policy,
        tuple(service),
    )
