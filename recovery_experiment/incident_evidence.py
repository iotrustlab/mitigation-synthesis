"""Typed, deterministic raw incident evidence for the synthetic recovery plant."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class EvidenceValidationError(ValueError):
    """Raised when raw evidence is malformed rather than merely incomplete."""


class EvidenceQuality(str, Enum):
    GOOD = "good"
    DEGRADED = "degraded"
    INVALID = "invalid"


class ResourceStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


def _finite_timestamp(value: float, field: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise EvidenceValidationError(f"{field} must be a finite numeric timestamp")


def _identifier(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceValidationError(f"{field} must be a nonempty string")


def _value(value: object, field: str) -> None:
    if not isinstance(value, (str, int, float, bool)) or value is None:
        raise EvidenceValidationError(f"{field} must be a JSON scalar")
    if isinstance(value, float) and not math.isfinite(value):
        raise EvidenceValidationError(f"{field} must be finite")


@dataclass(frozen=True)
class Observation:
    timestamp: float
    source: str
    signal: str
    value: str | int | float | bool
    unit: str | None
    quality: EvidenceQuality
    provenance_id: str

    def __post_init__(self) -> None:
        _finite_timestamp(self.timestamp, "observation timestamp")
        _identifier(self.source, "observation source")
        _identifier(self.signal, "observation signal")
        _value(self.value, "observation value")
        _identifier(self.provenance_id, "observation provenance_id")
        if self.unit is not None:
            _identifier(self.unit, "observation unit")

    def as_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "source": self.source,
            "signal": self.signal,
            "value": self.value,
            "unit": self.unit,
            "quality": self.quality.value,
            "provenance_id": self.provenance_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "Observation":
        return cls(
            timestamp=_number(data, "timestamp"),
            source=_string(data, "source"),
            signal=_string(data, "signal"),
            value=data.get("value"),
            unit=_optional_string(data, "unit"),
            quality=_enum(EvidenceQuality, data, "quality"),
            provenance_id=_string(data, "provenance_id"),
        )


@dataclass(frozen=True)
class CommandEvent:
    timestamp: float
    component: str
    command: str
    command_source: str | None
    authorized: bool | None
    provenance_id: str

    def __post_init__(self) -> None:
        _finite_timestamp(self.timestamp, "command timestamp")
        _identifier(self.component, "command component")
        _identifier(self.command, "command")
        _identifier(self.provenance_id, "command provenance_id")
        if self.command_source is not None:
            _identifier(self.command_source, "command source")
        if self.authorized is not None and type(self.authorized) is not bool:
            raise EvidenceValidationError("command authorized must be boolean or null")

    def as_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "component": self.component,
            "command": self.command,
            "command_source": self.command_source,
            "authorized": self.authorized,
            "provenance_id": self.provenance_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "CommandEvent":
        authorized = data.get("authorized")
        return cls(
            timestamp=_number(data, "timestamp"),
            component=_string(data, "component"),
            command=_string(data, "command"),
            command_source=_optional_string(data, "command_source"),
            authorized=authorized if authorized is None or type(authorized) is bool else _invalid_authorized(),
            provenance_id=_string(data, "provenance_id"),
        )


@dataclass(frozen=True)
class Alert:
    timestamp: float
    alert_type: str
    component: str | None
    severity: str
    confidence: float | None
    provenance_id: str

    def __post_init__(self) -> None:
        _finite_timestamp(self.timestamp, "alert timestamp")
        _identifier(self.alert_type, "alert type")
        _identifier(self.severity, "alert severity")
        _identifier(self.provenance_id, "alert provenance_id")
        if self.component is not None:
            _identifier(self.component, "alert component")
        if self.confidence is not None and (
            not isinstance(self.confidence, (int, float))
            or isinstance(self.confidence, bool)
            or not 0.0 <= self.confidence <= 1.0
        ):
            raise EvidenceValidationError("alert confidence must be between zero and one")

    def as_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "alert_type": self.alert_type,
            "component": self.component,
            "severity": self.severity,
            "confidence": self.confidence,
            "provenance_id": self.provenance_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "Alert":
        confidence = data.get("confidence")
        return cls(
            timestamp=_number(data, "timestamp"),
            alert_type=_string(data, "alert_type"),
            component=_optional_string(data, "component"),
            severity=_string(data, "severity"),
            confidence=None if confidence is None else _number(data, "confidence"),
            provenance_id=_string(data, "provenance_id"),
        )


@dataclass(frozen=True)
class ResourceObservation:
    timestamp: float
    resource: str
    status: ResourceStatus
    source: str
    confidence: float | None
    provenance_id: str

    def __post_init__(self) -> None:
        _finite_timestamp(self.timestamp, "resource timestamp")
        _identifier(self.resource, "resource")
        _identifier(self.source, "resource source")
        _identifier(self.provenance_id, "resource provenance_id")
        if self.confidence is not None and (
            not isinstance(self.confidence, (int, float))
            or isinstance(self.confidence, bool)
            or not 0.0 <= self.confidence <= 1.0
        ):
            raise EvidenceValidationError("resource confidence must be between zero and one")

    def as_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "resource": self.resource,
            "status": self.status.value,
            "source": self.source,
            "confidence": self.confidence,
            "provenance_id": self.provenance_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "ResourceObservation":
        confidence = data.get("confidence")
        return cls(
            timestamp=_number(data, "timestamp"),
            resource=_string(data, "resource"),
            status=_enum(ResourceStatus, data, "status"),
            source=_string(data, "source"),
            confidence=None if confidence is None else _number(data, "confidence"),
            provenance_id=_string(data, "provenance_id"),
        )


@dataclass(frozen=True)
class IncidentEvidence:
    """Raw telemetry, command history, and alerts with deterministic JSON I/O."""

    scenario_id: str
    window_start: float
    window_end: float
    observations: tuple[Observation, ...]
    alerts: tuple[Alert, ...]
    command_events: tuple[CommandEvent, ...]
    resource_observations: tuple[ResourceObservation, ...]
    metadata: Mapping[str, str]

    def __post_init__(self) -> None:
        _identifier(self.scenario_id, "scenario_id")
        _finite_timestamp(self.window_start, "window_start")
        _finite_timestamp(self.window_end, "window_end")
        if self.window_end < self.window_start:
            raise EvidenceValidationError("evidence window_end must not precede window_start")
        provenance = [
            item.provenance_id
            for items in (self.observations, self.alerts, self.command_events, self.resource_observations)
            for item in items
        ]
        if len(provenance) != len(set(provenance)):
            raise EvidenceValidationError("evidence provenance identifiers must be globally unique")
        for item in (*self.observations, *self.alerts, *self.command_events, *self.resource_observations):
            if not self.window_start <= item.timestamp <= self.window_end:
                raise EvidenceValidationError("evidence item timestamp is outside the incident window")
        if any(not isinstance(key, str) or not isinstance(value, str) for key, value in self.metadata.items()):
            raise EvidenceValidationError("incident metadata must be string-to-string")

    def as_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "observations": [item.as_dict() for item in self.observations],
            "alerts": [item.as_dict() for item in self.alerts],
            "command_events": [item.as_dict() for item in self.command_events],
            "resource_observations": [item.as_dict() for item in self.resource_observations],
            "metadata": dict(sorted(self.metadata.items())),
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "IncidentEvidence":
        return cls(
            scenario_id=_string(data, "scenario_id"),
            window_start=_number(data, "window_start"),
            window_end=_number(data, "window_end"),
            observations=tuple(Observation.from_dict(item) for item in _list_of_dicts(data, "observations")),
            alerts=tuple(Alert.from_dict(item) for item in _list_of_dicts(data, "alerts")),
            command_events=tuple(CommandEvent.from_dict(item) for item in _list_of_dicts(data, "command_events")),
            resource_observations=tuple(
                ResourceObservation.from_dict(item) for item in _list_of_dicts(data, "resource_observations")
            ),
            metadata=_string_mapping(data, "metadata"),
        )

    @classmethod
    def from_json(cls, text: str) -> "IncidentEvidence":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise EvidenceValidationError(f"incident evidence is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise EvidenceValidationError("incident evidence JSON must be an object")
        return cls.from_dict(data)


def _string(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EvidenceValidationError(f"{key} must be a nonempty string")
    return value


def _optional_string(data: Mapping[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise EvidenceValidationError(f"{key} must be a nonempty string or null")
    return value


def _number(data: Mapping[str, object], key: str) -> float:
    value = data.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise EvidenceValidationError(f"{key} must be a finite number")
    return float(value)


def _enum(enum_type: type[Enum], data: Mapping[str, object], key: str) -> Any:
    value = data.get(key)
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceValidationError(f"{key} has an unsupported value") from exc


def _list_of_dicts(data: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    value = data.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise EvidenceValidationError(f"{key} must be a list of objects")
    return value


def _string_mapping(data: Mapping[str, object], key: str) -> Mapping[str, str]:
    value = data.get(key, {})
    if not isinstance(value, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()):
        raise EvidenceValidationError(f"{key} must be an object of string values")
    return dict(value)


def _invalid_authorized() -> None:
    raise EvidenceValidationError("authorized must be boolean or null")
