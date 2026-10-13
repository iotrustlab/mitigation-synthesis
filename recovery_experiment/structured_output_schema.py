"""Fail-closed JSON-Schema adaptation for constrained model generation.

The canonical schema remains the acceptance contract.  A serving schema is a
backend-specific constrained-decoding approximation and is never suitable for
accepting model output.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Mapping


SERVING_SCHEMA_POLICY_VERSION = "serving-schema-adaptation-v1"
REVIEWED_GENERATION_ONLY_REMOVALS = frozenset({"uniqueItems"})

COMPATIBLE = "COMPATIBLE"
COMPATIBLE_WITH_CLIENT_VALIDATION = "COMPATIBLE_WITH_CLIENT_VALIDATION"
INCOMPATIBLE = "INCOMPATIBLE"


@dataclass(frozen=True)
class BackendSchemaCapabilities:
    """Structured-output limitations known for one serving backend."""

    backend: str
    unsupported_generation_keywords: frozenset[str] = frozenset()
    backend_version: str | None = None

    def __post_init__(self) -> None:
        if not self.backend.strip():
            raise ValueError("serving backend must be nonempty")
        if any(
            not isinstance(keyword, str) or not keyword
            for keyword in self.unsupported_generation_keywords
        ):
            raise ValueError("unsupported generation keywords must be nonempty strings")


@dataclass(frozen=True)
class SchemaConstraintOccurrence:
    """One constraint at a schema-object JSON path."""

    path: str
    keyword: str
    value: object

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "keyword": self.keyword,
            "value": copy.deepcopy(self.value),
        }


@dataclass(frozen=True)
class ServingSchemaPlan:
    """Serving schema plus the complete reproducibility/preflight report."""

    serving_schema: dict[str, object]
    backend: str
    backend_version: str | None
    canonical_schema_hash: str
    serving_schema_hash: str
    canonical_constraint_count: int
    serving_constraint_count: int
    removed_generation_constraints: tuple[SchemaConstraintOccurrence, ...]
    unsupported_unhandled_constraints: tuple[SchemaConstraintOccurrence, ...]
    status: str

    def report_dict(self) -> dict[str, object]:
        return {
            "policy_version": SERVING_SCHEMA_POLICY_VERSION,
            "serving_backend": self.backend,
            "serving_backend_version": self.backend_version,
            "canonical_schema_hash": self.canonical_schema_hash,
            "serving_schema_hash": self.serving_schema_hash,
            "canonical_constraint_count": self.canonical_constraint_count,
            "serving_constraint_count": self.serving_constraint_count,
            "removed_generation_constraint_count": len(
                self.removed_generation_constraints
            ),
            "removed_generation_constraints": [
                item.as_dict() for item in self.removed_generation_constraints
            ],
            "unsupported_unhandled_constraint_count": len(
                self.unsupported_unhandled_constraints
            ),
            "unsupported_unhandled_constraints": [
                item.as_dict() for item in self.unsupported_unhandled_constraints
            ],
            "status": self.status,
        }


def schema_sha256(schema: Mapping[str, object]) -> str:
    """Hash deterministic JSON serialization of a schema document."""

    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def capabilities_for_serving_backend(
    profile: str, *, backend_version: str | None = None
) -> BackendSchemaCapabilities:
    """Return a reviewed capability profile, rejecting invented profiles."""

    normalized = profile.strip().lower()
    if normalized in {"canonical", "full-json-schema"}:
        return BackendSchemaCapabilities(
            "full JSON Schema",
            backend_version=backend_version,
        )
    if normalized in {"vllm", "vllm-auto"}:
        return BackendSchemaCapabilities(
            "vLLM auto (xgrammar with guidance fallback)",
            frozenset({"uniqueItems"}),
            backend_version,
        )
    raise ValueError(
        f"unknown serving-schema capability profile {profile!r}; "
        "expected canonical or vllm-auto"
    )


def build_serving_schema(
    canonical_schema: Mapping[str, object],
    backend_capabilities: BackendSchemaCapabilities,
) -> ServingSchemaPlan:
    """Build a non-mutating serving approximation under a reviewed policy.

    Only keywords that are both reported unsupported by the selected backend
    and present in ``REVIEWED_GENERATION_ONLY_REMOVALS`` are removed.  Any
    other reported unsupported keyword makes the plan incompatible.
    """

    if not isinstance(canonical_schema, Mapping):
        raise TypeError("canonical schema must be a mapping")
    removed: list[SchemaConstraintOccurrence] = []
    unhandled: list[SchemaConstraintOccurrence] = []
    serving = _copy_schema_node(
        canonical_schema,
        "$",
        backend_capabilities,
        removed,
        unhandled,
    )
    removed_tuple = tuple(sorted(removed, key=_occurrence_sort_key))
    unhandled_tuple = tuple(sorted(unhandled, key=_occurrence_sort_key))
    status = (
        INCOMPATIBLE
        if unhandled_tuple
        else COMPATIBLE_WITH_CLIENT_VALIDATION
        if removed_tuple
        else COMPATIBLE
    )
    return ServingSchemaPlan(
        serving_schema=serving,
        backend=backend_capabilities.backend,
        backend_version=backend_capabilities.backend_version,
        canonical_schema_hash=schema_sha256(canonical_schema),
        serving_schema_hash=schema_sha256(serving),
        canonical_constraint_count=count_schema_constraints(canonical_schema),
        serving_constraint_count=count_schema_constraints(serving),
        removed_generation_constraints=removed_tuple,
        unsupported_unhandled_constraints=unhandled_tuple,
        status=status,
    )


def count_schema_constraints(schema: Mapping[str, object]) -> int:
    """Count validation/applicator keyword occurrences in schema positions."""

    if not isinstance(schema, Mapping):
        raise TypeError("schema must be a mapping")
    return _count_schema_node(schema)


# These sets also make traversal schema-context-aware.  In particular, an
# instance property literally named ``uniqueItems`` is not mistaken for the
# schema keyword of the same name.
_SCHEMA_MAP_KEYWORDS = frozenset(
    {"properties", "patternProperties", "$defs", "definitions", "dependentSchemas"}
)
_SCHEMA_LIST_KEYWORDS = frozenset(
    {"allOf", "anyOf", "oneOf", "prefixItems"}
)
_SINGLE_SCHEMA_KEYWORDS = frozenset(
    {
        "additionalProperties",
        "additionalItems",
        "contains",
        "contentSchema",
        "else",
        "if",
        "items",
        "not",
        "propertyNames",
        "then",
        "unevaluatedItems",
        "unevaluatedProperties",
    }
)
_SCHEMA_OR_LIST_KEYWORDS = frozenset({"items"})

# Annotation keywords intentionally are not counted.  This fixed vocabulary
# makes reports comparable rather than counting arbitrary dictionary keys or
# instance property names.
_CONSTRAINT_KEYWORDS = frozenset(
    {
        "$dynamicRef",
        "$ref",
        "additionalItems",
        "additionalProperties",
        "allOf",
        "anyOf",
        "const",
        "contains",
        "dependentRequired",
        "dependentSchemas",
        "else",
        "enum",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "if",
        "items",
        "maxContains",
        "maxItems",
        "maxLength",
        "maxProperties",
        "maximum",
        "minContains",
        "minItems",
        "minLength",
        "minProperties",
        "minimum",
        "multipleOf",
        "not",
        "oneOf",
        "pattern",
        "patternProperties",
        "prefixItems",
        "properties",
        "propertyNames",
        "required",
        "then",
        "type",
        "unevaluatedItems",
        "unevaluatedProperties",
        "uniqueItems",
    }
)


def _copy_schema_node(
    schema: Mapping[str, object],
    path: str,
    capabilities: BackendSchemaCapabilities,
    removed: list[SchemaConstraintOccurrence],
    unhandled: list[SchemaConstraintOccurrence],
) -> dict[str, object]:
    copied: dict[str, object] = {}
    for keyword, value in schema.items():
        if keyword in capabilities.unsupported_generation_keywords:
            occurrence = SchemaConstraintOccurrence(
                path, keyword, copy.deepcopy(value)
            )
            if keyword in REVIEWED_GENERATION_ONLY_REMOVALS:
                removed.append(occurrence)
                continue
            unhandled.append(occurrence)
        keyword_path = _append_json_path(path, keyword)
        copied[keyword] = _copy_keyword_value(
            keyword,
            value,
            keyword_path,
            capabilities,
            removed,
            unhandled,
        )
    return copied


def _copy_keyword_value(
    keyword: str,
    value: object,
    path: str,
    capabilities: BackendSchemaCapabilities,
    removed: list[SchemaConstraintOccurrence],
    unhandled: list[SchemaConstraintOccurrence],
) -> object:
    if keyword in _SCHEMA_MAP_KEYWORDS and isinstance(value, Mapping):
        return {
            name: _copy_schema_node(
                child,
                _append_json_path(path, str(name)),
                capabilities,
                removed,
                unhandled,
            )
            if isinstance(child, Mapping)
            else copy.deepcopy(child)
            for name, child in value.items()
        }
    if keyword in _SCHEMA_LIST_KEYWORDS and isinstance(value, list):
        return [
            _copy_schema_node(
                child,
                f"{path}[{index}]",
                capabilities,
                removed,
                unhandled,
            )
            if isinstance(child, Mapping)
            else copy.deepcopy(child)
            for index, child in enumerate(value)
        ]
    if keyword in _SINGLE_SCHEMA_KEYWORDS:
        if isinstance(value, Mapping):
            return _copy_schema_node(
                value, path, capabilities, removed, unhandled
            )
        if keyword in _SCHEMA_OR_LIST_KEYWORDS and isinstance(value, list):
            return [
                _copy_schema_node(
                    child,
                    f"{path}[{index}]",
                    capabilities,
                    removed,
                    unhandled,
                )
                if isinstance(child, Mapping)
                else copy.deepcopy(child)
                for index, child in enumerate(value)
            ]
    return copy.deepcopy(value)


def _count_schema_node(schema: Mapping[str, object]) -> int:
    count = sum(keyword in _CONSTRAINT_KEYWORDS for keyword in schema)
    for keyword, value in schema.items():
        if keyword in _SCHEMA_MAP_KEYWORDS and isinstance(value, Mapping):
            count += sum(
                _count_schema_node(child)
                for child in value.values()
                if isinstance(child, Mapping)
            )
        elif keyword in _SCHEMA_LIST_KEYWORDS and isinstance(value, list):
            count += sum(
                _count_schema_node(child)
                for child in value
                if isinstance(child, Mapping)
            )
        elif keyword in _SINGLE_SCHEMA_KEYWORDS:
            if isinstance(value, Mapping):
                count += _count_schema_node(value)
            elif keyword in _SCHEMA_OR_LIST_KEYWORDS and isinstance(value, list):
                count += sum(
                    _count_schema_node(child)
                    for child in value
                    if isinstance(child, Mapping)
                )
    return count


def _append_json_path(path: str, key: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        return f"{path}.{key}"
    return f"{path}[{json.dumps(key)}]"


def _occurrence_sort_key(
    occurrence: SchemaConstraintOccurrence,
) -> tuple[str, str]:
    return occurrence.path, occurrence.keyword
