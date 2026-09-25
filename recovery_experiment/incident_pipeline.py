"""Offline incident-evidence pipeline feeding the existing recovery core.

This module deliberately performs no online theorem proving and issues no
control command.  It only interprets evidence, validates the trust boundary,
and consults the already-reviewed local formal artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .candidate_context import CandidateRecoveryContext
from .context_grounding import GroundingResult, GroundingStatus
from .context_grounding import ground_candidate_context
from .formal_problem import TemplateFormalProblemAssessment, assess_template_formal_problems
from .incident_evidence import IncidentEvidence
from .incident_interpreter import DeterministicIncidentInterpreter, IncidentInterpreter
from .recovery_selection import RecoverySelection, incident_from_context, select_recovery_policy
from .trusted_plant_knowledge import RecoveryConfiguration, TrustedPlantKnowledge


class IncidentPipelineStatus(str, Enum):
    GROUNDED_AND_ASSESSED = "GROUNDED_AND_ASSESSED"
    GROUNDING_FAILED = "GROUNDING_FAILED"
    DOWNSTREAM_INVALID = "DOWNSTREAM_INVALID"


@dataclass(frozen=True)
class IncidentPipelineResult:
    """Traceable output of the evidence-to-selection pipeline.

    ``formal_assessment`` and ``selection`` are absent after a grounding
    failure.  This is a deliberate safety boundary, rather than a partial
    recovery recommendation.
    """

    status: IncidentPipelineStatus
    evidence: IncidentEvidence
    candidate: CandidateRecoveryContext
    grounding: GroundingResult
    formal_assessment: TemplateFormalProblemAssessment | None
    selection: RecoverySelection | None
    reasons: tuple[str, ...]
    online_prover_invoked: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "evidence": self.evidence.as_dict(),
            "candidate": self.candidate.as_dict(),
            "grounding": self.grounding.as_dict(),
            "formal_assessment": None
            if self.formal_assessment is None
            else self.formal_assessment.as_dict(),
            "selection": None if self.selection is None else self.selection.as_dict(),
            "reasons": list(self.reasons),
            "online_prover_invoked": self.online_prover_invoked,
            "proof_scope": "Existing certificate checkers only; this runner never invokes CLEO.",
        }


def run_incident_pipeline(
    evidence: IncidentEvidence,
    trusted_plant_knowledge: TrustedPlantKnowledge,
    recovery_configuration: RecoveryConfiguration,
    *,
    interpreter: IncidentInterpreter | None = None,
) -> IncidentPipelineResult:
    """Interpret evidence, ground it, then use existing offline assurance.

    The future ``LLMIncidentInterpreter`` must implement ``IncidentInterpreter``
    and return the same ``CandidateRecoveryContext``.  It cannot bypass this
    grounding function or pass raw evidence directly to the formal core.
    """

    interpreter = interpreter or DeterministicIncidentInterpreter()
    candidate = interpreter.interpret(evidence)
    grounding = ground_candidate_context(candidate, trusted_plant_knowledge, recovery_configuration)
    if not grounding.succeeded:
        return IncidentPipelineResult(
            IncidentPipelineStatus.GROUNDING_FAILED,
            evidence,
            candidate,
            grounding,
            None,
            None,
            (
                "formal construction and recovery selection were not invoked because the candidate did not ground",
                *grounding.reasons,
            ),
        )

    assert grounding.grounded is not None
    context = grounding.grounded.context
    formal_assessment = assess_template_formal_problems(context)
    try:
        incident = incident_from_context(
            context,
            required_delivered_flow=recovery_configuration.required_delivered_flow,
            require_continuous_delivery=recovery_configuration.require_continuous_delivery,
            permitted_interruption_duration=recovery_configuration.permitted_interruption_duration,
            recovery_deadline=context.plant.transfer_recovery_deadline,
            attacker_schedule=grounding.grounded.attacker_schedule,
        )
        selection = select_recovery_policy(incident)
    except (ValueError, TypeError) as exc:
        return IncidentPipelineResult(
            IncidentPipelineStatus.DOWNSTREAM_INVALID,
            evidence,
            candidate,
            grounding,
            formal_assessment,
            None,
            (f"grounded context could not be assessed by the existing recovery core: {exc}",),
        )
    return IncidentPipelineResult(
        IncidentPipelineStatus.GROUNDED_AND_ASSESSED,
        evidence,
        candidate,
        grounding,
        formal_assessment,
        selection,
        (
            "grounding succeeded; formal construction, certificate checks, and selection used existing offline artifacts",
            "no online CLEO invocation was performed",
        ),
    )
