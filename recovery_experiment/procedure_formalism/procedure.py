"""Procedure, resource and provenance types shared by the three case studies."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from enum import Enum
from math import isfinite
from types import MappingProxyType


class DependencyStatus(str, Enum):
    TRUSTED = "TRUSTED"
    COMPROMISED = "COMPROMISED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class EvidenceStatus(str, Enum):
    SOURCE_BACKED = "SOURCE_BACKED"
    RESEARCH_AUTHORED = "RESEARCH_AUTHORED"
    OBSERVED_IN_TRACE = "OBSERVED_IN_TRACE"
    FORMALLY_PROVED = "FORMALLY_PROVED"
    UNKNOWN = "UNKNOWN"


class DependencyKind(str, Enum):
    HUMAN_ACTOR = "HUMAN_ACTOR"
    SOFTWARE_ACTOR = "SOFTWARE_ACTOR"
    INTERFACE = "INTERFACE"
    COMMUNICATION_PATH = "COMMUNICATION_PATH"
    CONTROLLER = "CONTROLLER"
    OUTPUT_STAGE = "OUTPUT_STAGE"
    ACTUATOR = "ACTUATOR"
    POWER_SOURCE = "POWER_SOURCE"
    PHYSICAL_PROCESS = "PHYSICAL_PROCESS"
    OBSERVER = "OBSERVER"
    SERVICE = "SERVICE"
    PROTECTION = "PROTECTION"


class ProcedureEvent(str, Enum):
    REQUEST_ISSUED = "REQUEST_ISSUED"
    CONTROLLER_ACCEPTED = "CONTROLLER_ACCEPTED"
    CONTROLLER_OUTPUT_SET = "CONTROLLER_OUTPUT_SET"
    ACTUATION_DELIVERED = "ACTUATION_DELIVERED"
    ACTUATOR_RESPONDED = "ACTUATOR_RESPONDED"
    PHYSICAL_SERVICE_PRESENT = "PHYSICAL_SERVICE_PRESENT"
    SERVICE_OBSERVED = "SERVICE_OBSERVED"
    SERVICE_ESTABLISHED = "SERVICE_ESTABLISHED"


class ProcedureStatus(str, Enum):
    PROVED = "PROVED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _labels(values, field_name):
    if not isinstance(values, tuple) or not all(_text(value) for value in values):
        raise ValueError(f"{field_name} must be a tuple of nonempty strings")
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} has repeated entries")


@dataclass(frozen=True)
class DependencyNode:
    node_id: str
    kind: DependencyKind
    status: DependencyStatus
    owner: str
    required_by: tuple[str, ...]
    source_status: EvidenceStatus
    provenance: str
    threat_effect: str
    notes: str

    def __post_init__(self):
        if not all(_text(x) for x in (self.node_id, self.owner, self.provenance, self.threat_effect)):
            raise ValueError("a dependency needs an identity, owner, provenance and threat effect")
        if not isinstance(self.kind, DependencyKind):
            raise ValueError("invalid dependency kind")
        if not isinstance(self.status, DependencyStatus):
            raise ValueError("invalid operational dependency status")
        if not isinstance(self.source_status, EvidenceStatus):
            raise ValueError("invalid source/evidence status")
        if not self.required_by:
            raise ValueError("a dependency must identify its procedures")
        _labels(self.required_by, "required_by")
        if not isinstance(self.notes, str):
            raise ValueError("dependency notes must be a string")


@dataclass(frozen=True, kw_only=True)
class RecoveryProcedure:
    procedure_id: str
    case_id: str
    version: str
    actor: str | None
    role: str
    actor_ready_time: int | None
    authority_requirements: tuple[str, ...]
    interface: str | None
    communication_path: str | None
    controller: str | None
    controller_guard: str
    controller_transition: str
    output_stage: str | None
    delivered_actuation_relation: str
    actuator: str | None
    plant_model: str | None
    observer: str | None
    observation_relation: str
    freshness_requirement: str
    service_definition: str
    safety_definition: str
    initial_state: Mapping[str, bool | int | float | str | None]
    deadline: int | None
    horizon: int | None
    required_dependencies: Mapping[str, DependencyNode]
    shared_dependencies: tuple[str, ...]
    attacker_effects: Mapping[str, str]
    cost_vector_definition: tuple[str, ...]
    source_references: tuple[str, ...]
    evidence_status_by_field: Mapping[str, EvidenceStatus]

    def __post_init__(self):
        # Freeze copies of the containers while retaining each shared node by identity.
        for key in ("initial_state", "required_dependencies", "attacker_effects", "evidence_status_by_field"):
            mapping = getattr(self, key)
            if not isinstance(mapping, Mapping) or not all(_text(k) for k in mapping):
                raise ValueError(f"{key} must be a mapping with nonempty string keys")
            object.__setattr__(self, key, MappingProxyType(dict(mapping)))

        for key in ("procedure_id", "case_id", "version", "role", "controller_guard", "controller_transition",
                    "delivered_actuation_relation", "observation_relation", "freshness_requirement",
                    "service_definition", "safety_definition"):
            if not _text(getattr(self, key)):
                raise ValueError(f"{key} must be nonempty")
        if self.plant_model is not None and not _text(self.plant_model):
            raise ValueError("use a model identity or None for plant_model")
        for key in ("actor_ready_time", "deadline", "horizon"):
            value = getattr(self, key)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{key} must be nonnegative integer ticks or None")
        if self.deadline is not None and self.horizon is not None and self.deadline > self.horizon:
            raise ValueError("deadline falls outside analysis horizon")
        for key in ("authority_requirements", "shared_dependencies", "source_references", "cost_vector_definition"):
            _labels(getattr(self, key), key)
        if not self.source_references:
            raise ValueError("procedure needs at least one provenance reference")
        for key, value in self.initial_state.items():
            if value is not None and type(value) not in (str, bool, int, float):
                raise ValueError(f"invalid state value for {key}")
            if isinstance(value, float) and not isfinite(value):
                raise ValueError(f"nonfinite state value for {key}")

        for key, node in self.required_dependencies.items():
            if not isinstance(node, DependencyNode) or key != node.node_id or self.procedure_id not in node.required_by:
                raise ValueError(f"invalid dependency binding for {key}")
        for key in ("actor", "interface", "communication_path", "controller", "output_stage", "actuator", "observer"):
            node_id = getattr(self, key)
            if node_id is not None and node_id not in self.required_dependencies:
                raise ValueError(f"unbound {key} dependency")
        for node_id in self.shared_dependencies:
            node = self.required_dependencies.get(node_id)
            if node is None or len(node.required_by) < 2:
                raise ValueError(f"unbound or unshared dependency {node_id}")
        if set(self.attacker_effects) - self.required_dependencies.keys():
            raise ValueError("threat effect references an unbound dependency")
        if not all(_text(effect) for effect in self.attacker_effects.values()):
            raise ValueError("invalid threat effect")
        if self.evidence_status_by_field.keys() != field_evidence().keys():
            raise ValueError("missing or unknown procedure evidence fields")
        if not all(isinstance(e, EvidenceStatus) for e in self.evidence_status_by_field.values()):
            raise ValueError("invalid procedure evidence status")

    def as_dict(self) -> dict:
        """Return independent JSON data with node identities preserved by their keys."""
        def serialize(value):
            if isinstance(value, Enum):
                return value.value
            if isinstance(value, (DependencyNode, RecoveryProcedure)):
                return {field.name: serialize(getattr(value, field.name)) for field in fields(value)}
            if isinstance(value, Mapping):
                return {key: serialize(item) for key, item in value.items()}
            if isinstance(value, tuple):
                return [serialize(item) for item in value]
            return value
        return serialize(self)


def field_evidence(default: EvidenceStatus = EvidenceStatus.UNKNOWN, **overrides: EvidenceStatus):
    """Give each field an explicit evidence status, including unknown quantities."""
    result = {f.name: default for f in fields(RecoveryProcedure) if f.name != "evidence_status_by_field"}
    if overrides.keys() - result.keys():
        raise ValueError("unknown field in provenance overrides")
    return {**result, **overrides}
