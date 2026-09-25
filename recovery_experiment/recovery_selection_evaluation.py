"""Deterministic evaluation scenarios for certificate-based policy selection."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter

from .recovery_selection import (
    CertificatePaths,
    RecoveryIncident,
    RecoverySelection,
    incident_from_context,
    select_recovery_policy,
)
from .model import AttackerAction, PlantParameters, PlantState
from .scenarios import context_for, named_contexts


@dataclass(frozen=True)
class SelectionScenario:
    description: str
    incident: RecoveryIncident
    certificate_paths: CertificatePaths = CertificatePaths()


def selection_scenarios() -> dict[str, SelectionScenario]:
    """Common-incident cases that separate certificate scope from requirements."""

    baseline = named_contexts()["baseline_feasible"]
    delayed = context_for(
        replace(
            PlantParameters(),
            isolation_delay=1.0,
            backup_startup_delay=1.5,
            transfer_recovery_deadline=1.5,
        )
    )
    margin_outside = context_for(baseline.plant, PlantState(x1=10.5, x2=6.0))
    missing_isolation = replace(
        baseline,
        available_recovery_resources={"backup_capacity": baseline.plant.backup_capacity, "primary_isolation": False},
    )
    return {
        "flowing_service_qualified": SelectionScenario(
            "Flowing takeover is covered and provides the requested uninterrupted 1.2 service.",
            incident_from_context(baseline, require_continuous_delivery=True),
        ),
        "state_margin_fallback_to_hold": SelectionScenario(
            "T1 is safe but too near overflow for flowing startup; full-horizon safety hold interruption is permitted.",
            incident_from_context(
                margin_outside,
                required_delivered_flow=0.0,
                require_continuous_delivery=False,
                permitted_interruption_duration=margin_outside.plant.horizon,
            ),
        ),
        "both_covered_cost_comparison": SelectionScenario(
            "Both distinct templates are covered when full-horizon interruption is permitted; compare common-demand costs.",
            incident_from_context(
                baseline,
                required_delivered_flow=0.0,
                require_continuous_delivery=False,
                permitted_interruption_duration=baseline.plant.horizon,
            ),
        ),
        "uninterrupted_service_rules_out_hold": SelectionScenario(
            "The same physical incident requires continuous 1.2 delivery, excluding controlled hold.",
            incident_from_context(baseline, require_continuous_delivery=True),
        ),
        "delayed_flowing_service_qualified": SelectionScenario(
            "Only the delayed-isolation flowing policy is physically applicable and it covers continuous 1.2 service.",
            incident_from_context(
                delayed,
                require_continuous_delivery=True,
                attacker_schedule=(
                    AttackerAction.FORCE_PRIMARY_OFF,
                    AttackerAction.FORCE_PRIMARY_ON,
                ),
            ),
        ),
        "neither_meets_full_external_delivery": SelectionScenario(
            "Continuous full 1.5 external demand is required; flowing startup proves only 1.2.",
            incident_from_context(
                baseline,
                required_delivered_flow=baseline.plant.downstream_demand,
                require_continuous_delivery=True,
            ),
        ),
        "missing_trusted_isolation": SelectionScenario(
            "The incident omits the trusted physical isolation resource, so neither context is valid.",
            incident_from_context(missing_isolation, require_continuous_delivery=False),
        ),
        "untrusted_flowing_certificate": SelectionScenario(
            "A noncanonical flowing-certificate path cannot authorize that policy.",
            incident_from_context(baseline, require_continuous_delivery=False),
            CertificatePaths(flowing_takeover=Path("unreviewed-flowing-manifest.json")),
        ),
        "incompatible_topology": SelectionScenario(
            "Only the synthetic parallel-pump topology is selectable.",
            incident_from_context(
                baseline,
                require_continuous_delivery=False,
                topology_id="unsupported-topology-v1",
            ),
        ),
    }


def evaluate_selection_scenarios(
    *, simulate_for_diagnostics: bool = True
) -> dict[str, object]:
    """Run every deterministic scenario without invoking CLEO."""

    results: dict[str, object] = {}
    for name, scenario in selection_scenarios().items():
        selection: RecoverySelection = select_recovery_policy(
            scenario.incident,
            certificate_paths=scenario.certificate_paths,
            simulate_for_diagnostics=simulate_for_diagnostics,
        )
        results[name] = {
            "description": scenario.description,
            "selection": selection.as_dict(),
        }
    return {
        "scope": (
            "This selects only among fixed, offline-verified synthetic policies compatible with the "
            "incident's physical isolation timing; it does not synthesize a strategy or establish "
            "real-world trust assumptions."
        ),
        "offline_proofs": {
            "controlled_hold_seconds": 9.09929197000747,
            "flowing_takeover_seconds": 9.85577582300175,
            "delayed_isolation_flowing_takeover_seconds": 19.196509931003675,
            "included_in_online_latency": False,
        },
        "formal_horizons": {
            "immediate_isolation": {
                "startup_duration": 1.0,
                "post_takeover_operation_duration": 5.0,
                "total_duration": 6.0,
                "verification_command": "python -m recovery_experiment.verify_common_horizon",
            },
            "delayed_isolation": {
                "startup_duration": 1.5,
                "post_takeover_operation_duration": 4.5,
                "total_duration": 6.0,
                "verification_command": "$CLEO_PYTHON -m recovery_experiment.verify_delayed_isolation_recovery",
                "note": "The delayed symbolic theorem admits any positive T; this evaluation binds T=4.5 seconds.",
            },
            "online_note": "Selection reads reviewed certificates and never invokes CLEO.",
        },
        "scenarios": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate certificate-based recovery policy selection.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("recovery_experiment/results/recovery-selection-evaluation.json"),
    )
    parser.add_argument(
        "--without-simulation",
        action="store_true",
        help="measure certificate/admissibility selection without diagnostic traces or trace-derived costs",
    )
    args = parser.parse_args()
    started = perf_counter()
    report = evaluate_selection_scenarios(simulate_for_diagnostics=not args.without_simulation)
    report["evaluation_elapsed_ms"] = (perf_counter() - started) * 1_000
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
