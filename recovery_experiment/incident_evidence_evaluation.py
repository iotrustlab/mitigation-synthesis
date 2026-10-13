"""Gold-dataset evaluation and first-divergence analysis for incident intake."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .incident_dataset import SyntheticIncidentCase, SyntheticIncidentDataset, build_synthetic_incident_dataset
from .incident_pipeline import IncidentPipelineResult, run_incident_pipeline


class ErrorPropagationCategory(str, Enum):
    NO_DIVERGENCE = "NO_DIVERGENCE"
    INTERPRETATION_ERROR = "INTERPRETATION_ERROR"
    GROUNDING_ERROR = "GROUNDING_ERROR"
    TEMPLATE_SELECTION_ERROR = "TEMPLATE_SELECTION_ERROR"
    FORMAL_MODEL_SELECTION_ERROR = "FORMAL_MODEL_SELECTION_ERROR"
    CERTIFICATE_SELECTION_ERROR = "CERTIFICATE_SELECTION_ERROR"
    SERVICE_ADMISSIBILITY_ERROR = "SERVICE_ADMISSIBILITY_ERROR"
    COST_SELECTION_ERROR = "COST_SELECTION_ERROR"


@dataclass(frozen=True)
class Accuracy:
    correct: int
    total: int

    @property
    def value(self) -> float:
        return 1.0 if self.total == 0 else self.correct / self.total

    def as_dict(self) -> dict[str, object]:
        return {"correct": self.correct, "total": self.total, "accuracy": self.value}


@dataclass(frozen=True)
class GroundingMetrics:
    correct_acceptance: int
    correct_rejection: int
    false_acceptance: int
    false_rejection: int
    status_accuracy: Accuracy

    def as_dict(self) -> dict[str, object]:
        return {
            "correct_acceptance": self.correct_acceptance,
            "correct_rejection": self.correct_rejection,
            "false_acceptance": self.false_acceptance,
            "false_rejection": self.false_rejection,
            "status_accuracy": self.status_accuracy.as_dict(),
        }


@dataclass(frozen=True)
class CaseEvaluation:
    scenario_id: str
    field_matches: tuple[tuple[str, bool | None], ...]
    grounding_match: bool
    grounding_succeeded: bool
    template_match: bool | None
    formal_model_match: bool | None
    certificate_match: bool | None
    service_match: bool | None
    selection_match: bool | None
    first_divergence: ErrorPropagationCategory

    def as_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "field_matches": dict(self.field_matches),
            "grounding_match": self.grounding_match,
            "grounding_succeeded": self.grounding_succeeded,
            "template_match": self.template_match,
            "formal_model_match": self.formal_model_match,
            "certificate_match": self.certificate_match,
            "service_match": self.service_match,
            "selection_match": self.selection_match,
            "first_divergence": self.first_divergence.value,
        }


@dataclass(frozen=True)
class IncidentEvidenceEvaluation:
    dataset_seed: int
    case_count: int
    field_accuracy: tuple[tuple[str, Accuracy], ...]
    grounding: GroundingMetrics
    template_accuracy: Accuracy
    formal_model_accuracy: Accuracy
    certificate_accuracy: Accuracy
    service_accuracy: Accuracy
    recovery_decision_accuracy: Accuracy
    first_divergence_counts: tuple[tuple[str, int], ...]
    cases: tuple[CaseEvaluation, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "dataset_seed": self.dataset_seed,
            "case_count": self.case_count,
            "field_accuracy": {name: result.as_dict() for name, result in self.field_accuracy},
            "grounding": self.grounding.as_dict(),
            "template_accuracy": self.template_accuracy.as_dict(),
            "formal_model_accuracy": self.formal_model_accuracy.as_dict(),
            "certificate_accuracy": self.certificate_accuracy.as_dict(),
            "service_accuracy": self.service_accuracy.as_dict(),
            "recovery_decision_accuracy": self.recovery_decision_accuracy.as_dict(),
            "first_divergence_counts": dict(self.first_divergence_counts),
            "cases": [case.as_dict() for case in self.cases],
        }


def evaluate_deterministic_pipeline(
    dataset: SyntheticIncidentDataset | None = None,
) -> IncidentEvidenceEvaluation:
    """Compare the no-CLEO deterministic runner to independently declared gold."""

    dataset = dataset or build_synthetic_incident_dataset()
    evaluations = tuple(_evaluate_case(case) for case in dataset.cases)
    field_names = tuple(name for name, _ in dataset.cases[0].gold.candidate_values)
    field_accuracy = tuple(
        (
            name,
            Accuracy(
                sum(dict(case.field_matches)[name] is True for case in evaluations),
                sum(dict(case.field_matches)[name] is not None for case in evaluations),
            ),
        )
        for name in field_names
    )
    grounding_matches = sum(case.grounding_match for case in evaluations)
    ground_expected = [case.gold.grounding_status.value == "GROUNDED_CONTEXT" for case in dataset.cases]
    ground_actual = [case.grounding_succeeded for case in evaluations]
    correct_acceptance = sum(expected and actual for expected, actual in zip(ground_expected, ground_actual))
    correct_rejection = sum(not expected and not actual for expected, actual in zip(ground_expected, ground_actual))
    false_acceptance = sum(not expected and actual for expected, actual in zip(ground_expected, ground_actual))
    false_rejection = sum(expected and not actual for expected, actual in zip(ground_expected, ground_actual))
    applicable_cases = [case for case in evaluations if case.template_match is not None]
    divergence_counts = tuple(
        (category.value, sum(case.first_divergence is category for case in evaluations))
        for category in ErrorPropagationCategory
    )
    return IncidentEvidenceEvaluation(
        dataset.seed,
        len(dataset.cases),
        field_accuracy,
        GroundingMetrics(
            correct_acceptance,
            correct_rejection,
            false_acceptance,
            false_rejection,
            Accuracy(grounding_matches, len(evaluations)),
        ),
        _accuracy(applicable_cases, "template_match"),
        _accuracy(applicable_cases, "formal_model_match"),
        _accuracy(applicable_cases, "certificate_match"),
        _accuracy(applicable_cases, "service_match"),
        _accuracy(applicable_cases, "selection_match"),
        divergence_counts,
        evaluations,
    )


def _accuracy(cases: list[CaseEvaluation], attribute: str) -> Accuracy:
    return Accuracy(sum(getattr(case, attribute) is True for case in cases), len(cases))


def _evaluate_case(case: SyntheticIncidentCase) -> CaseEvaluation:
    result = run_incident_pipeline(case.evidence, case.trusted_plant_knowledge, case.recovery_configuration)
    return evaluate_incident_pipeline_result(case, result)


def evaluate_incident_pipeline_result(
    case: SyntheticIncidentCase,
    result: IncidentPipelineResult,
) -> CaseEvaluation:
    """Compare one already-executed pipeline result with its declared gold.

    Keeping this comparison separate lets an external interpreter be called
    exactly once while reusing the same downstream metrics as the deterministic
    baseline.  Gold labels are consumed only here, after interpretation.
    """

    if result.evidence.scenario_id != case.scenario_id:
        raise ValueError("pipeline result does not belong to the supplied evaluation case")
    field_matches = tuple(
        (name, _actual_field_value(result, name) == expected)
        for name, expected in case.gold.candidate_values
    )
    grounding_match = result.grounding.status is case.gold.grounding_status
    if not result.grounding.succeeded:
        field_matches = _mark_ungrounded_fields_not_applicable(field_matches)
        divergence = _first_divergence(field_matches, grounding_match, None, None, None, None, None)
        return CaseEvaluation(
            case.scenario_id,
            field_matches,
            grounding_match,
            False,
            None,
            None,
            None,
            None,
            None,
            divergence,
        )

    assert result.formal_assessment is not None
    actual_templates = tuple(
        template.template_id.value
        for template in result.formal_assessment.templates
        if template.applicability.applicable
    )
    actual_models = tuple(
        (template.template_id.value, None if template.construction is None else template.construction.formal_model_id)
        for template in result.formal_assessment.templates
        if template.applicability.applicable
    )
    actual_certificates = tuple(
        (template.template_id.value, None if template.certificate is None else template.certificate.status.value)
        for template in result.formal_assessment.templates
        if template.applicability.applicable
    )
    actual_service = (
        ()
        if result.selection is None
        else tuple(
            sorted(
                (candidate.policy, candidate.status.value)
                for candidate in result.selection.candidates
            )
        )
    )
    template_match = actual_templates == case.gold.applicable_templates
    formal_match = actual_models == case.gold.formal_models
    certificate_match = actual_certificates == case.gold.certificate_statuses
    service_match = actual_service == tuple(sorted(case.gold.service_statuses))
    selection_match = result.selection is not None and (
        result.selection.status.value == case.gold.selection_status
        and result.selection.selected_policy == case.gold.selected_policy
    )
    divergence = _first_divergence(
        field_matches,
        grounding_match,
        template_match,
        formal_match,
        certificate_match,
        service_match,
        selection_match,
    )
    return CaseEvaluation(
        case.scenario_id,
        field_matches,
        grounding_match,
        True,
        template_match,
        formal_match,
        certificate_match,
        service_match,
        selection_match,
        divergence,
    )


def _actual_field_value(result: IncidentPipelineResult, field: str) -> object | None:
    candidate = result.candidate
    if field == "hold_controls_available":
        if not result.grounding.grounded:
            return None
        availability = result.grounding.grounded.context.resource_availability
        return availability.trusted_inflow_control_available and availability.trusted_demand_control_available
    if field == "backup_trusted":
        if not result.grounding.grounded:
            return None
        resource = next(item for item in result.grounding.grounded.resource_groundings if item.resource == "P2")
        return resource.trusted_for_incident and resource.controllable_by_recovery
    if field == "isolation_available":
        if not result.grounding.grounded:
            return None
        return result.grounding.grounded.context.resource_availability.trusted_isolation_available
    claims = {
        "suspected_compromised_component": candidate.suspected_compromised_component,
        "attacker_capability": candidate.attacker_capability,
        "x1": candidate.x1,
        "x2": candidate.x2,
        "backup_operational": candidate.backup_operational,
        "isolation_operational": candidate.isolation_operational,
        "isolation_delay": candidate.isolation_delay,
    }
    return claims[field].value


def _mark_ungrounded_fields_not_applicable(
    field_matches: tuple[tuple[str, bool], ...],
) -> tuple[tuple[str, bool | None], ...]:
    """Trust/authority is not evaluated when the grounding gate correctly stops."""

    grounded_only = {"backup_trusted", "isolation_available", "hold_controls_available"}
    return tuple((name, None if name in grounded_only else match) for name, match in field_matches)


def _first_divergence(
    field_matches: tuple[tuple[str, bool | None], ...],
    grounding_match: bool,
    template_match: bool | None,
    formal_match: bool | None,
    certificate_match: bool | None,
    service_match: bool | None,
    selection_match: bool | None,
) -> ErrorPropagationCategory:
    if any(match is False for _, match in field_matches):
        return ErrorPropagationCategory.INTERPRETATION_ERROR
    if not grounding_match:
        return ErrorPropagationCategory.GROUNDING_ERROR
    if template_match is False:
        return ErrorPropagationCategory.TEMPLATE_SELECTION_ERROR
    if formal_match is False:
        return ErrorPropagationCategory.FORMAL_MODEL_SELECTION_ERROR
    if certificate_match is False:
        return ErrorPropagationCategory.CERTIFICATE_SELECTION_ERROR
    if service_match is False:
        return ErrorPropagationCategory.SERVICE_ADMISSIBILITY_ERROR
    if selection_match is False:
        return ErrorPropagationCategory.COST_SELECTION_ERROR
    return ErrorPropagationCategory.NO_DIVERGENCE
