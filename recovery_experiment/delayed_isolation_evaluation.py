"""Deterministic evaluation of the constructed delayed-isolation incident model.

Simulation is diagnostic. The delayed theorem is verified, but no certificate
is issued here, so no positive-delay run is authorized by certificate coverage.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, replace
from itertools import product
from pathlib import Path
from time import perf_counter

from .context import RecoveryContext
from .cost import RecoveryCost, calculate_cost
from .experiment import run_scenario
from .formal_problem import assess_incident_formal_problem
from .model import AttackerAction, PlantParameters, PlantState
from .policies import (
    ScheduledPrimaryAttacker,
    TrustedDelayedIsolationFlowingBackupTakeoverPolicy,
    TrustedFlowingBackupTakeoverPolicy,
)
from .recovery_selection import incident_from_context, select_recovery_policy
from .scenarios import context_for, named_contexts


@dataclass(frozen=True)
class DelayedIsolationScenario:
    description: str
    context: RecoveryContext
    attacker_schedule: tuple[AttackerAction, ...] | None


DELAYED_BINARY_SCHEDULES = tuple(
    tuple(actions)
    for actions in product(
        (AttackerAction.FORCE_PRIMARY_OFF, AttackerAction.FORCE_PRIMARY_ON), repeat=2
    )
)


def _delayed_parameters(**changes: float) -> PlantParameters:
    """The first symbolic family has two delay and three startup control slices."""

    return replace(
        PlantParameters(),
        isolation_delay=1.0,
        backup_startup_delay=1.5,
        transfer_recovery_deadline=1.5,
        **changes,
    )


def delayed_isolation_scenarios() -> dict[str, DelayedIsolationScenario]:
    baseline = named_contexts()["baseline_feasible"]
    delayed = _delayed_parameters()
    safe_delayed = context_for(delayed)
    t1_margin_failure = context_for(delayed, PlantState(x1=9.8, x2=6.0))
    t2_on_failure = context_for(delayed, PlantState(x1=7.0, x2=8.8))
    insufficient_backup = context_for(_delayed_parameters(backup_capacity=1.0))
    timing_outside = context_for(replace(PlantParameters(), isolation_delay=0.5, backup_startup_delay=1.0))
    missing_isolation = replace(
        safe_delayed,
        available_recovery_resources={"backup_capacity": delayed.backup_capacity, "primary_isolation": False},
    )
    return {
        "immediate_baseline": DelayedIsolationScenario(
            "Existing immediate-isolation flowing certificate baseline.",
            baseline,
            (AttackerAction.FORCE_PRIMARY_OFF,),
        ),
        "delayed_safe_command_change": DelayedIsolationScenario(
            "P1 is forced off then on during the two pending-isolation control intervals.",
            safe_delayed,
            (
                AttackerAction.FORCE_PRIMARY_OFF,
                AttackerAction.FORCE_PRIMARY_ON,
            ),
        ),
        "delayed_t1_margin_insufficient": DelayedIsolationScenario(
            "P1-off during delayed isolation drives the upstream tank toward its high bound.",
            t1_margin_failure,
            (AttackerAction.FORCE_PRIMARY_OFF, AttackerAction.FORCE_PRIMARY_OFF),
        ),
        "delayed_t2_on_threat": DelayedIsolationScenario(
            "P1-on during delayed isolation drives the downstream tank toward its high bound.",
            t2_on_failure,
            (AttackerAction.FORCE_PRIMARY_ON, AttackerAction.FORCE_PRIMARY_ON),
        ),
        "delayed_insufficient_backup": DelayedIsolationScenario(
            "Backup capacity is below the formal qbackup >= qmin requirement; stored T2 water can still mask it briefly.",
            insufficient_backup,
            (AttackerAction.FORCE_PRIMARY_OFF, AttackerAction.FORCE_PRIMARY_OFF),
        ),
        "delayed_timing_outside_family": DelayedIsolationScenario(
            "Positive delay is explicit but does not match the first theorem timing family.",
            timing_outside,
            (AttackerAction.FORCE_PRIMARY_OFF, AttackerAction.FORCE_PRIMARY_OFF),
        ),
        "delayed_missing_isolation": DelayedIsolationScenario(
            "No trusted physical isolation resource is declared, so construction is invalid.",
            missing_isolation,
            None,
        ),
    }


def _simulate(scenario: DelayedIsolationScenario) -> dict[str, object] | None:
    if scenario.attacker_schedule is None:
        return None
    p = scenario.context.plant
    delayed = p.isolation_delay > 0
    attacker = ScheduledPrimaryAttacker(scenario.attacker_schedule)
    defender = (
        TrustedDelayedIsolationFlowingBackupTakeoverPolicy()
        if delayed
        else TrustedFlowingBackupTakeoverPolicy()
    )
    result = run_scenario(
        "delayed_isolation_evaluation",
        p,
        attacker,
        defender,
        initial_state=scenario.context.current_state,
    )
    observed_cost = calculate_cost(
        result,
        "trusted_delayed_isolation_flowing_backup_takeover" if delayed else "trusted_flowing_backup_takeover",
        scenario.context.recovery_cost_parameters,
        service_target=p.downstream_demand,
    )
    estimated_cost = _estimate_cost(scenario.context, delayed)
    return {
        "safe_in_simulation": result.safe,
        "continuous_minimum_service_in_simulation": all(
            row.q_delivered >= p.min_service_flow for row in result.records
        ),
        "recovery_established_at": result.final_state.recovery_established_at,
        "nominal_contract_minimum_cost": estimated_cost.as_dict(),
        "estimated_recovery_cost": estimated_cost.as_dict(),
        "observed_simulated_cost": observed_cost.as_dict(),
        "formal_cost_bound": None,
        "cost_interpretation": {
            "nominal_contract_minimum": (
                "A procedure-level estimate with zero service loss because startup delivery is "
                "evaluated against qmin, not against the external demand target."
            ),
            "observed_simulated": (
                "A deterministic trace cost evaluated against external downstream demand. It is "
                "not a hybrid-game cost bound or deployment measurement."
            ),
        },
        "transition_trace": [
            row.as_dict()
            for row in result.records
            if row.timestamp <= p.backup_startup_delay + 1e-12
        ],
    }


def _estimate_cost(context: RecoveryContext, delayed: bool) -> RecoveryCost:
    """Estimate the fixed procedure before looking at a simulated trace.

    This is a nominal contract-minimum estimate: it values startup delivery at
    the theorem's qmin threshold, so its service-loss term is zero. It does not
    represent a selected attacker trajectory, a worst-case cost, safety, or
    certificate coverage; those are reported separately.
    """

    p = context.plant
    weights = context.recovery_cost_parameters
    recovery_duration = max(p.backup_startup_delay, p.isolation_delay) if delayed else p.backup_startup_delay
    backup_usage = p.backup_capacity * max(0.0, p.horizon - recovery_duration)
    intervention_cost = weights.takeover_intervention_cost
    total = (
        weights.recovery_time_weight * recovery_duration
        + weights.intervention_weight * intervention_cost
        + weights.backup_usage_weight * backup_usage
    )
    return RecoveryCost(0.0, recovery_duration, intervention_cost, backup_usage, total)


def enumerate_delayed_schedule_costs(context: RecoveryContext) -> dict[str, object]:
    """Exhaustively simulate the theorem's four finite P1 command pairs.

    This is a deterministic simulator study, not an optimization proof.  The
    implemented ``J`` contains service shortfall, recovery duration,
    intervention, and P2 usage, but no term for P1 flow or tank-level motion.
    Consequently the four schedules change the transient tank trace here while
    producing the same cost components for the safe baseline.
    """

    rows: list[dict[str, object]] = []
    for schedule in DELAYED_BINARY_SCHEDULES:
        result = run_scenario(
            "delayed_isolation_schedule_enumeration",
            context.plant,
            ScheduledPrimaryAttacker(schedule),
            TrustedDelayedIsolationFlowingBackupTakeoverPolicy(),
            initial_state=context.current_state,
        )
        cost = calculate_cost(
            result,
            "trusted_delayed_isolation_flowing_backup_takeover",
            context.recovery_cost_parameters,
            service_target=context.plant.downstream_demand,
        )
        rows.append(
            {
                "attacker_schedule": [action.value for action in schedule],
                "safe_in_simulation": result.safe,
                "continuous_minimum_service_in_simulation": all(
                    row.q_delivered >= context.plant.min_service_flow for row in result.records
                ),
                "observed_simulated_cost": cost.as_dict(),
                "pre_isolation_tank_state": [
                    {"timestamp": row.timestamp, "x1": row.x1, "x2": row.x2, "q1": row.q1}
                    for row in result.records[:2]
                ],
            }
        )
    conservative = max(rows, key=lambda row: float(row["observed_simulated_cost"]["total"]))
    nominal = _estimate_cost(context, delayed=True)
    observed = conservative["observed_simulated_cost"]
    return {
        "scope": (
            "All four binary P1 command pairs represented by the finite delayed theorem and deterministic "
            "simulator; not a formally proved hybrid-game cost bound."
        ),
        "nominal_contract_minimum_cost": nominal.as_dict(),
        "observed_costs_by_schedule": rows,
        "conservative_finite_schedule_cost": observed,
        "term_by_term_reconciliation": {
            "service_loss": {
                "nominal": nominal.service_loss,
                "observed": observed["service_loss"],
                "weighted_difference": context.recovery_cost_parameters.service_loss_weight
                * (observed["service_loss"] - nominal.service_loss),
                "explanation": (
                    "Startup qdelivered is 1.2 for 1.5 seconds. The nominal value compares it to qmin=1.2; "
                    "the observed trace compares it to external demand=1.5, yielding 0.3*1.5=0.45 shortfall."
                ),
            },
            "recovery_duration": {
                "nominal": nominal.recovery_duration,
                "observed": observed["recovery_duration"],
                "explanation": "Both use the P2 availability time of 1.5 seconds.",
            },
            "intervention_cost": {
                "nominal": nominal.intervention_cost,
                "observed": observed["intervention_cost"],
                "explanation": "Both charge the fixed trusted takeover intervention cost of 2.0.",
            },
            "backup_usage": {
                "nominal": nominal.backup_usage,
                "observed": observed["backup_usage"],
                "explanation": "Both count P2 flow 1.5 over the post-startup 4.5-second interval: 6.75.",
            },
            "total": {"nominal": nominal.total, "observed": observed["total"]},
            "primary_path_contribution": (
                "P1 changes the first two tank-state transitions but J has no P1-flow or tank-level term, so "
                "the four safe schedules have equal observed J in this model."
            ),
        },
    }


def evaluate_delayed_isolation_scenarios() -> dict[str, object]:
    """Report construction, certificate, and simulation separately for each incident."""

    scenarios: dict[str, object] = {}
    for name, scenario in delayed_isolation_scenarios().items():
        assessment = assess_incident_formal_problem(scenario.context)
        simulation = _simulate(scenario) if assessment.construction.status.value != "INVALID_INCIDENT_CONTEXT" else None
        selection = select_recovery_policy(
            incident_from_context(
                scenario.context,
                require_continuous_delivery=True,
                attacker_schedule=scenario.attacker_schedule,
            )
        )
        scenarios[name] = {
            "description": scenario.description,
            "attacker_schedule": None
            if scenario.attacker_schedule is None
            else [action.value for action in scenario.attacker_schedule],
            "formal_assessment": assessment.as_dict(),
            "recovery_selection": selection.as_dict(),
            "selected_recovery_policy": selection.selected_policy,
            "simulation": simulation,
        }
    return {
        "scope": (
            "Immediate and the first explicit delayed-isolation configuration are constructed separately. "
            "Each is authorized only by its matching reviewed certificate when its exact assumptions hold."
        ),
        "delayed_safe_schedule_cost_reconciliation": enumerate_delayed_schedule_costs(
            delayed_isolation_scenarios()["delayed_safe_command_change"].context
        ),
        "scenarios": scenarios,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate immediate and delayed-isolation incident construction.")
    parser.add_argument(
        "--output", type=Path, default=Path("recovery_experiment/results/delayed-isolation-evaluation.json")
    )
    args = parser.parse_args()
    started = perf_counter()
    report = evaluate_delayed_isolation_scenarios()
    report["evaluation_elapsed_ms"] = (perf_counter() - started) * 1_000
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
