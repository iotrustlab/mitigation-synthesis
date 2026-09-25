"""Deterministic A--G evaluation of resource-dependent recovery construction."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, replace
from pathlib import Path

from .context import RecoveryContext
from .formal_problem import TemplateFormalProblemAssessment, assess_template_formal_problems
from .model import PlantState
from .recovery_selection import RecoveryIncident, incident_from_context, select_recovery_policy
from .scenarios import context_for, named_contexts


@dataclass(frozen=True)
class ResourceAwareScenario:
    description: str
    context: RecoveryContext
    incident: RecoveryIncident


def _with_resources(context: RecoveryContext, **availability: bool) -> RecoveryContext:
    """Change only incident authority; physical topology and components stay fixed."""

    return replace(
        context,
        resource_availability=replace(context.resource_availability, **availability),
    )


def resource_aware_scenarios() -> dict[str, ResourceAwareScenario]:
    """Build every required resource/service/state combination without CLEO."""

    baseline = named_contexts()["baseline_feasible"]
    backup_unavailable = _with_resources(baseline, trusted_backup_available=False)
    no_isolation = _with_resources(baseline, trusted_isolation_available=False)
    missing_hold_gate = _with_resources(
        baseline,
        trusted_backup_available=False,
        trusted_demand_control_available=False,
    )
    high_t1 = context_for(baseline.plant, PlantState(x1=10.5, x2=6.0))
    interruption_allowed = dict(
        required_delivered_flow=0.0,
        require_continuous_delivery=False,
        permitted_interruption_duration=baseline.plant.horizon,
    )
    return {
        "A_backup_available": ResourceAwareScenario(
            "Trusted isolation and P2 make takeover applicable; the independently controlled safe hold also applies.",
            baseline,
            incident_from_context(baseline, **interruption_allowed),
        ),
        "B_backup_unavailable_hold": ResourceAwareScenario(
            "P2 is unavailable for this incident, but trusted isolation plus both hold gates construct safe hold.",
            backup_unavailable,
            incident_from_context(backup_unavailable, **interruption_allowed),
        ),
        "C_positive_continuous_service_without_backup": ResourceAwareScenario(
            "Safe hold remains safety-certified, but a positive uninterrupted-service request excludes it.",
            backup_unavailable,
            incident_from_context(backup_unavailable, require_continuous_delivery=True),
        ),
        "D_both_resources_interruption_allowed": ResourceAwareScenario(
            "Both templates are certificate-covered with interruption allowed, so only then are trace costs compared.",
            baseline,
            incident_from_context(baseline, **interruption_allowed),
        ),
        "E_no_trusted_isolation": ResourceAwareScenario(
            "Neither implemented template can be constructed without a trusted independent isolator.",
            no_isolation,
            incident_from_context(no_isolation, **interruption_allowed),
        ),
        "F_missing_trusted_hold_gate": ResourceAwareScenario(
            "Without P2 and a trusted downstream-curtailment gate, no implemented template applies.",
            missing_hold_gate,
            incident_from_context(missing_hold_gate, **interruption_allowed),
        ),
        "G_takeover_margin_outside_hold_applies": ResourceAwareScenario(
            "T1 is within plant safety but outside flowing-startup margin; immediate safe hold remains covered.",
            high_t1,
            incident_from_context(high_t1, **interruption_allowed),
        ),
    }


def evaluate_resource_aware_recovery() -> dict[str, object]:
    """Report construction, certificate coverage, selection, trace, and cost for A--G."""

    scenarios: dict[str, object] = {}
    for name, scenario in resource_aware_scenarios().items():
        formal: TemplateFormalProblemAssessment = assess_template_formal_problems(scenario.context)
        selection = select_recovery_policy(scenario.incident)
        scenarios[name] = {
            "description": scenario.description,
            "incident_resources": {
                "physical_components": scenario.context.as_dict()["physical_components"],
                "control_path_authority": scenario.context.as_dict()["control_path_authority"],
                "template_availability": scenario.context.as_dict()["resource_availability"],
            },
            "template_applicability": formal.applicability.as_dict(),
            "formal_problem_assessment": formal.as_dict(),
            "selection": selection.as_dict(),
        }
    return {
        "scope": (
            "Resource availability is incident-specific trusted operational authority. The evaluation is offline, "
            "synthetic, and trace-derived; it neither deploys nor synthesizes a new controller."
        ),
        "cost_interpretation": {
            "external_demand": "unchanged plant downstream demand for every candidate",
            "formal_cost_bound": None,
            "note": "Costs are compared only after certificate and service-contract admissibility."
        },
        "scenarios": scenarios,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate resource-aware recovery templates A--G.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("recovery_experiment/results/resource-aware-recovery-evaluation.json"),
    )
    args = parser.parse_args()
    report = evaluate_resource_aware_recovery()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
