"""Attleboro 2019 design slice with explicitly assumed resource states.

All durations in this fixture count 100 ms surrogate scans. One call creates
a single incident snapshot. Every candidate in that snapshot uses the same
selector state and refers to the same downstream components.
"""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite

from .procedure import (
    DependencyKind as Kind,
    DependencyNode,
    DependencyStatus,
    EvidenceStatus,
    RecoveryProcedure,
    field_evidence,
)


REMOTE_ID = "attleboro-remote-end-to-end-recovery-v1"
HAND_ID = "attleboro-local-hand-v1"
HOLD_ID = "attleboro-hold-v1"
SOURCE_VERSION = "ec3319f9d3ac41352df2a21253f4af3aab7f22ca"
PLANT_MODEL = "attleboro-sampled-flow-and-start-delay-v1"
COST_COMPONENTS = (
    "service_deficit", "restoration_delay", "human_effort", "intervention_count",
    "resource_use", "evidence_gap_duration",
)
SOURCE_MAP = "recovery_experiment/attleboro/source_to_model_map.md"
SOURCE_REFS = (
    SOURCE_MAP,
    f"sphere-usecases Attleboro case tree {SOURCE_VERSION}",
    "controller ST sha256 e0fb9a37b81bc43820e5b525666f1b998615cfbfc438bdd46305db28f17119cc",
    "simulator ST sha256 51b8380cc7a68e05725f1427438541c596b44eb7f9eb2e153f61c8012c89a1e1",
)

_INITIAL = {
    "utility": 1, "mts_generator": 0, "generator_running": 0, "generator_ready": 0,
    "reset_pending": 0, "reset_request": 0, "previous_reset": 0,
    "remote_selected": 1, "hand_selected": 0, "trip": 0, "ph_out_of_range": 0,
    "flow_blocked": 0, "observation_fresh": 1, "authorized": 1, "initial_flow": 0,
}
_SHARED = ("vfd", "pump", "motor_power", "trip_path", "water_path", "observer")
_REMOTE = ("remote_operator", "ows", "communication", "plc", "delivery")
_HAND = ("local_operator", "hand_panel")
_SOURCE = EvidenceStatus.SOURCE_BACKED
_AUTHORED = EvidenceStatus.RESEARCH_AUTHORED


def _resources(statuses):
    # Locators describe the basis for the *role*. All availability and integrity
    # assignments below are research assumptions, including for documented roles.
    definitions = {
        "remote_operator": (Kind.HUMAN_ACTOR, "remote operations", "OWS momentary Start",
                            "operator request bit", "Authorized actor ready at the console."),
        "ows": (Kind.INTERFACE, "operator interface", "OWS momentary Start",
                "interface request bit", "Research interface availability."),
        "communication": (Kind.COMMUNICATION_PATH, "command path", "assumed OWS to PLC path",
                          "communicated request bit", "Physical network details are unknown."),
        "plc": (Kind.CONTROLLER, "remote controller", "power and reset authority logic",
                "controller output bit", "Source-derived guard with authored scan behavior."),
        "delivery": (Kind.OUTPUT_STAGE, "controller to simulator boundary", "delivered-start trace observation",
                     "delivered start bit independent of PLC output", "Research peer-side command boundary."),
        "local_operator": (Kind.HUMAN_ACTOR, "local operations", "Local Hand and hardwired trips",
                           "local request bit", "Research fixture declares presence and readiness."),
        "hand_panel": (Kind.INTERFACE, "local drive panel", "Local Hand and hardwired trips",
                       "Hand demand bit", "Panel request bypasses the remote PLC gate."),
        "vfd": (Kind.ACTUATOR, "shared drive", "Local Hand and hardwired trips",
                "drive enable bit", "One VFD serves both command locations."),
        "pump": (Kind.ACTUATOR, "shared pump", "run confirmation and flow observation",
                 "pump response bit", "Both commands target this pump."),
        "motor_power": (Kind.POWER_SOURCE, "shared motor supply", "utility and generator selection",
                        "motor power bit", "Computed from source selection and readiness."),
        "trip_path": (Kind.PROTECTION, "hardwired protection", "Local Hand and hardwired trips",
                      "protection permissive bit", "Combined hardwired trip gates both paths."),
        "water_path": (Kind.PHYSICAL_PROCESS, "forward-flow process", "forward flow and no-flow observation",
                       "flow passage bit", "Run feedback can coexist with blockage."),
        "observer": (Kind.OBSERVER, "meter and observation channel", "forward flow and no-flow observation",
                     "untrusted flow in {0,10} L/s and pressure in {30,90} psi",
                     "Both service claims require a credible fresh sample."),
    }
    if set(statuses) - definitions.keys():
        raise ValueError("unrecognized Attleboro dependency")
    nodes = {}
    for key, (kind, owner, locator, effect, note) in definitions.items():
        if key in _SHARED:
            required_by = (REMOTE_ID, HAND_ID)
        else:
            required_by = (REMOTE_ID,) if key in _REMOTE else (HAND_ID,)
        if key != "observer":
            effect = f"{effect} in {{0,1}}, held for the bounded procedure"
        nodes[key] = DependencyNode(
            key, kind, statuses.get(key, DependencyStatus.TRUSTED), owner, required_by,
            _AUTHORED, f"{SOURCE_MAP} ({locator})", effect, note,
        )
    return nodes


def attleboro(statuses: Mapping[str, DependencyStatus] | None = None,
             initial_state: Mapping[str, int | float] | None = None,
             local_ready_time: int = 0) -> dict[str, RecoveryProcedure]:
    """Construct candidates under one physical state; override statuses by node ID."""
    overrides = dict(initial_state or {})
    if overrides.keys() - _INITIAL.keys():
        raise ValueError("unrecognized Attleboro initial state field")
    state = {**_INITIAL, **overrides}
    for key, value in state.items():
        if key == "initial_flow":
            if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 10:
                raise ValueError("initial_flow must lie in the sampled model range [0,10] L/s")
        elif type(value) not in (bool, int) or value not in (0, 1):
            raise ValueError(f"{key} must be a Boolean value")
        else:
            state[key] = int(value)
    if state["ph_out_of_range"]:
        if "trip" in overrides and not state["trip"]:
            raise ValueError("the combined trip includes pH out of range")
        state["trip"] = 1

    nodes = _resources(dict(statuses or {}))
    common = dict(
        case_id="attleboro-2019-design-slice", version="1", initial_state=state,
        deadline=3, horizon=3, cost_vector_definition=COST_COMPONENTS, source_references=SOURCE_REFS,
    )
    pump = dict(
        **common, actuator="pump", plant_model=PLANT_MODEL, observer="observer",
        observation_relation="A healthy meter samples actual flow; a stale meter retains its prior value.",
        freshness_requirement="A trusted sample of the final scan at the deadline.",
        service_definition="Actual flow >= 5 L/s, pressure <= 90 psi, pH in range and trip clear; "
                           "establishment additionally requires a credible observed flow >= 5 L/s.",
        safety_definition="At each sample, 0 <= flow <= 10 L/s, pressure <= 90 psi, pH in range and trip clear.",
        shared_dependencies=_SHARED,
        evidence_status_by_field=field_evidence(
            _AUTHORED, interface=_SOURCE, actuator=_SOURCE, role=_SOURCE,
        ),
    )

    def bindings(ids):
        selected = {key: nodes[key] for key in ids}
        return dict(
            required_dependencies=selected,
            attacker_effects={key: node.threat_effect for key, node in selected.items()},
        )

    remote = RecoveryProcedure(
        **pump, **bindings(_REMOTE + _SHARED), procedure_id=REMOTE_ID,
        actor="remote_operator", role="remote operator", actor_ready_time=0,
        authority_requirements=("qualified OWS actor", "utility power", "MTS on utility", "generator idle",
                                "reset latch cleared", "Remote selected exclusively", "no trip"),
        interface="ows", communication_path="communication", controller="plc",
        controller_guard="Authorized request, good utility, generator idle, reset cleared, Remote selected and trip clear.",
        controller_transition="A rising Start creates pending demand. A subsequent run confirmation seals it "
                              "under the sampled remote authority guard.",
        output_stage="delivery",
        delivered_actuation_relation="A trusted delivery stage copies the controller start output to the drive.",
    )
    hand = RecoveryProcedure(
        **pump, **bindings(_HAND + _SHARED), procedure_id=HAND_ID,
        actor="local_operator", role="local drive operator", actor_ready_time=local_ready_time,
        authority_requirements=("qualified actor at Hand panel", "Hand selected exclusively", "motor power", "no trip"),
        interface="hand_panel", communication_path=None, controller="hand_panel",
        controller_guard="Local actor present and authorized, Hand selected exclusively and local demand active.",
        controller_transition="The drive's local mode accepts the panel demand.",
        output_stage="hand_panel",
        delivered_actuation_relation="Hand demand reaches the shared VFD locally; motor power and trip gate its effect.",
    )
    hold = RecoveryProcedure(
        **common, procedure_id=HOLD_ID, actor=None, role="passive hold", actor_ready_time=None,
        authority_requirements=("initial stopped state", "no start demand",),
        interface=None, communication_path=None, controller=None, output_stage=None, actuator=None,
        controller_guard="No start request is issued.", controller_transition="Maintain no-start.",
        delivered_actuation_relation="The hold issues no positive actuation demand.",
        plant_model=None, observer=None, observation_relation="No service observation required for no-start.",
        freshness_requirement="Inapplicable to no-start.", service_definition="No positive water-service claim.",
        safety_definition="The desired hold state has zero drive demand and the pump stopped.",
        shared_dependencies=(), **bindings(()), evidence_status_by_field=field_evidence(_AUTHORED),
    )
    return {"remote": remote, "hand": hand, "hold": hold}
