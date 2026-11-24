"""Representation-level hydro startup and CHP device lifecycle cases."""

from __future__ import annotations

from .cost_vector import COMPONENT_NAMES
from .procedure import (
    DependencyKind as Kind,
    DependencyNode,
    DependencyStatus,
    EvidenceStatus as Source,
    RecoveryProcedure,
    field_evidence,
)

RECEIPT = "PROCEDURE_EXPERIMENT_RECEIPT.md"
PUBLISHED = "iotrustlab/sphere-usecases@716e6d2e07ea00e7639f66567e3720fb6d1c2218"
HYDRO = f"{PUBLISHED}:sector-energy/merwin-hydro"
CHP = f"{PUBLISHED}:sector-energy/poland-2025-chp-recovery"

LOCAL_MANUAL = "merwin-local-manual"
LOCAL_AUTO = "merwin-local-auto"
REMOTE_AUTO = "merwin-hcc-remote-auto"
HYDRO_HOLD = "merwin-hold-no-start"
RESET = "chp-controller-reset"
RELOAD = "chp-reviewed-backup-reload"
CHP_HOLD = "chp-isolate-hold"
NO_ASSURANCE = "chp-no-assured-process-recovery"


def _node(name, kind, owner, users, source, description):
    return DependencyNode(
        node_id=name, kind=kind, status=DependencyStatus.UNKNOWN, owner=owner, required_by=users,
        source_status=Source.UNKNOWN, provenance=source, threat_effect="Threat alphabet unspecified in this representation",
        notes=description + " Operational trust has not been established.",
    )


def _bindings(nodes, procedure_id):
    required = {node.node_id: node for node in nodes if procedure_id in node.required_by}
    shared = tuple(key for key, node in required.items() if len(node.required_by) > 1)
    return dict(required_dependencies=required, shared_dependencies=shared, attacker_effects={})


def merwin_procedures() -> tuple[RecoveryProcedure, ...]:
    starts = (LOCAL_MANUAL, LOCAL_AUTO, REMOTE_AUTO)
    local = (LOCAL_MANUAL, LOCAL_AUTO)
    all_modes = (*starts, HYDRO_HOLD)
    source = HYDRO + "/source_assessment.md"

    def node(name, kind, owner, users, description):
        return _node(name, kind, owner, users, source, description)

    nodes = (
        node("local_operator", Kind.HUMAN_ACTOR, "station", (*local, HYDRO_HOLD), "Historical local operator role."),
        node("hcc_operator", Kind.HUMAN_ACTOR, "HCC", (REMOTE_AUTO,), "Historical HCC operator role."),
        node("panel", Kind.INTERFACE, "station", (*local, HYDRO_HOLD), "Local command interface."),
        node("scada", Kind.INTERFACE, "HCC", (REMOTE_AUTO,), "Remote-auto command interface."),
        node("hcc_link", Kind.COMMUNICATION_PATH, "representative backend", (REMOTE_AUTO,), "Research remote path."),
        node("lube", Kind.PHYSICAL_PROCESS, "station", local, "Guide-bearing lubrication and oil level."),
        node("auxiliaries", Kind.PHYSICAL_PROCESS, "station", (REMOTE_AUTO,), "Normal auxiliaries required in Remote Auto."),
        node("sequencer", Kind.CONTROLLER, "research controller", all_modes, "Mode-sensitive start logic."),
        node("synchronization", Kind.PROTECTION, "research backend", starts, "Synchronization before breaker close."),
        node("breaker_command", Kind.OUTPUT_STAGE, "research controller", starts, "Close output."),
        node("breaker", Kind.ACTUATOR, "research backend", starts, "Physical breaker contact."),
        node("hydro_unit", Kind.PHYSICAL_PROCESS, "research backend", starts, "Representative Olmsted-derived unit."),
        node("power_meter", Kind.OBSERVER, "research backend", starts, "Same-row contact and power observation."),
    )
    modes = {
        LOCAL_MANUAL: ("local_manual", "present local operator and normal lube pump and oil level",
                       "Accept local start. At speed accept local sync, then a fresh close request."),
        LOCAL_AUTO: ("local_auto", "present local operator and normal lube pump and oil level",
                     "Accept local start, then roll, synchronize and issue automatic close."),
        REMOTE_AUTO: ("remote_auto", "present HCC operator, working link and normal auxiliaries",
                      "Accept HCC start in remote-auto, then roll, synchronize and issue automatic close."),
        HYDRO_HOLD: ("hold", "withhold startup", "Issue no start request."),
    }
    procedures = []
    for procedure_id, (mode, authority, transition) in modes.items():
        remote = procedure_id == REMOTE_AUTO
        start = procedure_id != HYDRO_HOLD
        evidence = field_evidence(
            Source.RESEARCH_AUTHORED, actor=Source.SOURCE_BACKED, role=Source.SOURCE_BACKED,
            actor_ready_time=Source.UNKNOWN, authority_requirements=Source.SOURCE_BACKED if start else Source.RESEARCH_AUTHORED,
            horizon=Source.UNKNOWN, deadline=Source.UNKNOWN, observation_relation=Source.RESEARCH_AUTHORED,
            safety_definition=Source.UNKNOWN, freshness_requirement=Source.UNKNOWN, attacker_effects=Source.UNKNOWN,
        )
        procedures.append(RecoveryProcedure(
            procedure_id=procedure_id, case_id="merwin", version="1",
            actor="hcc_operator" if remote else "local_operator", role="HCC operator" if remote else "local operator",
            actor_ready_time=None, authority_requirements=(authority,), interface="scada" if remote else "panel",
            communication_path="hcc_link" if remote else None, controller="sequencer",
            controller_guard=authority, controller_transition=transition,
            output_stage="breaker_command" if start else None,
            delivered_actuation_relation="Require close output and later contact confirmation." if start else "Withhold start.",
            actuator="breaker" if start else None, plant_model="olmsted-derived-hydro-simulator" if start else None,
            observer="power_meter" if start else None,
            observation_relation=("Ordered speed, sync, close command, contact, then three consecutive same-row "
                                  "samples running with closed contact and at least 1 MW.") if start else "No generation credit.",
            freshness_requirement="Maximum acceptable observation age is unspecified.",
            service_definition="Initial representative grid generation." if start else "No positive generation claim.",
            safety_definition="Safe startup or continued hold bounds are unspecified.",
            initial_state={"selected_mode": mode, "site_initial_state": None},
            deadline=None, horizon=None, cost_vector_definition=COMPONENT_NAMES,
            source_references=(RECEIPT, source, HYDRO + "/evaluate.py"), evidence_status_by_field=evidence,
            **_bindings(nodes, procedure_id),
        ))
    return tuple(procedures)


def chp_procedures() -> tuple[RecoveryProcedure, ...]:
    device_work = (RESET, RELOAD)
    active = (*device_work, CHP_HOLD)
    source = CHP + "/source_assessment.md"

    def node(name, kind, owner, users, description):
        return _node(name, kind, owner, users, source, description)

    nodes = (
        node("engineer", Kind.HUMAN_ACTOR, "engineering", active, "Authorized engineering role."),
        node("engineering_access", Kind.INTERFACE, "engineering", active, "Fixture engineering access."),
        node("plc", Kind.CONTROLLER, "device fixture", device_work, "Bootability and loaded logic are distinct."),
        node("backup", Kind.INTERFACE, "engineering", (RELOAD,), "Available, compatible, reviewed backup."),
        node("heartbeat", Kind.OBSERVER, "device evaluator", (RELOAD,), "Disposable runtime scan counter."),
        node("process", Kind.PHYSICAL_PROCESS, "unknown", active, "Cogeneration plant and restart permissives."),
        node("customer_supply", Kind.SERVICE, "unknown", active, "Supply mechanism and observations unknown."),
    )
    procedures = []
    choices = {
        RESET: ("Engineering access.", "Attempt reset. Bootability depends on the device profile.",
                "Simulated reset and device log loss.", "Reset alone supplies no runtime evidence."),
        RELOAD: ("Engineering access, bootable device, available compatible reviewed backup.",
                 "Load reviewed logic after reset, then request runtime start.",
                 "Program load and runtime start are distinct lifecycle transitions.",
                 "Two increasing scan-counter reads on a disposable OpenPLC runtime witness benign execution."),
        CHP_HOLD: ("Engineering access. Isolation coverage is unknown.", "Withhold a process restart request.",
                   "Isolation and continued safe hold require independent confirmation.", "No process observer defined."),
        NO_ASSURANCE: ("No process procedure has established service.", "Record the assessment disposition.",
                       "No command issued.", "No process observer defined."),
    }
    for procedure_id, (guard, transition, delivery, observation) in choices.items():
        active_case = procedure_id != NO_ASSURANCE
        device = procedure_id in device_work
        reload = procedure_id == RELOAD
        evidence = field_evidence(
            Source.RESEARCH_AUTHORED, actor_ready_time=Source.UNKNOWN, horizon=Source.UNKNOWN, deadline=Source.UNKNOWN,
            plant_model=Source.UNKNOWN, service_definition=Source.UNKNOWN, safety_definition=Source.UNKNOWN,
            observation_relation=Source.OBSERVED_IN_TRACE if reload else Source.RESEARCH_AUTHORED,
            attacker_effects=Source.UNKNOWN, freshness_requirement=Source.UNKNOWN,
        )
        procedures.append(RecoveryProcedure(
            procedure_id=procedure_id, case_id="polish-chp", version="1",
            actor="engineer" if active_case else None, role="engineering operator" if active_case else "analysis disposition",
            actor_ready_time=None, authority_requirements=(guard,), interface="engineering_access" if active_case else None,
            communication_path=None, controller="plc" if device else None, controller_guard=guard,
            controller_transition=transition, output_stage=None, delivered_actuation_relation=delivery, actuator=None,
            plant_model=None, observer="heartbeat" if reload else None, observation_relation=observation,
            freshness_requirement="Process and customer-service observation contracts are unknown.",
            service_definition="Credible physical cogeneration and customer supply require separate evidence.",
            safety_definition="Site process readiness and safe restart bounds are unknown.",
            initial_state={"process_ready": None, "customer_supply_mechanism": None},
            deadline=None, horizon=None, cost_vector_definition=COMPONENT_NAMES,
            source_references=(RECEIPT, source, CHP + "/replay.py"), evidence_status_by_field=evidence,
            **_bindings(nodes, procedure_id),
        ))
    return tuple(procedures)
