"""Focused comparison of builder-generated immediate and delayed recovery games."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from time import perf_counter

from .cost import calculate_cost
from .experiment import run_scenario
from .formal_problem import assess_incident_formal_problem
from .model import AttackerAction, PlantParameters, PlantState
from .policies import (
    ScheduledPrimaryAttacker,
    TrustedDelayedIsolationFlowingBackupTakeoverPolicy,
    TrustedFlowingBackupTakeoverPolicy,
)
from .recovery_model_builder import build_recovery_problem
from .recovery_selection import incident_from_context, select_recovery_policy
from .scenarios import context_for


def _parameters(isolation_delay: float, startup_delay: float) -> PlantParameters:
    return replace(
        PlantParameters(),
        isolation_delay=isolation_delay,
        backup_startup_delay=startup_delay,
        transfer_recovery_deadline=startup_delay,
    )


def _numeric_margins(context) -> dict[str, float]:
    p, s = context.plant, context.current_state
    return {
        "t1_upper_startup": p.high_t1 - (s.x1 + p.startup_inflow_rate * p.backup_startup_delay),
        "t1_lower_primary_on_delay": s.x1
        + (p.startup_inflow_rate - p.primary_capacity) * p.isolation_delay
        - p.low_t1,
        "t2_lower_startup": s.x2 - p.startup_withdrawal_rate * p.backup_startup_delay - p.low_t2,
        "t2_upper_primary_on_delay": p.high_t2
        - (s.x2 + (p.primary_capacity - p.startup_withdrawal_rate) * p.isolation_delay),
    }


def _simulate(context, schedule: tuple[AttackerAction, ...]) -> dict[str, object]:
    delayed = context.plant.isolation_delay > 0
    result = run_scenario(
        "builder_evaluation",
        context.plant,
        ScheduledPrimaryAttacker(schedule),
        TrustedDelayedIsolationFlowingBackupTakeoverPolicy()
        if delayed
        else TrustedFlowingBackupTakeoverPolicy(),
        initial_state=context.current_state,
    )
    cost = calculate_cost(
        result,
        "trusted_delayed_isolation_flowing_backup_takeover"
        if delayed
        else "trusted_flowing_backup_takeover",
        context.recovery_cost_parameters,
        service_target=context.plant.downstream_demand,
    )
    return {
        "safe": result.safe,
        "continuous_minimum_service": all(
            row.q_delivered >= context.plant.min_service_flow for row in result.records
        ),
        "recovery_established_at": result.final_state.recovery_established_at,
        "cost": cost.as_dict(),
        "transition_trace": [
            {
                "timestamp": row.timestamp,
                "q1": row.q1,
                "q2": row.q2,
                "isolation_pending": row.isolation_pending_during_interval,
                "isolation_effective": row.isolation_effective_during_interval,
                "x1": row.x1,
                "x2": row.x2,
            }
            for row in result.records
            if row.timestamp <= context.plant.backup_startup_delay + 1e-12
        ],
    }


def _case(name: str, context, schedule: tuple[AttackerAction, ...]) -> dict[str, object]:
    started = perf_counter()
    generated = build_recovery_problem(context)
    construction = assess_incident_formal_problem(context)
    selection = select_recovery_policy(
        incident_from_context(
            context,
            require_continuous_delivery=True,
            attacker_schedule=schedule,
        )
    )
    return {
        "name": name,
        "context": context.as_dict(),
        "generated_problem": generated.as_dict(),
        "numeric_safety_margins": _numeric_margins(context),
        "formal_assessment": construction.as_dict(),
        "selection": selection.as_dict(),
        "simulation": _simulate(context, schedule),
        "local_construction_and_checking_latency_ms": (perf_counter() - started) * 1_000,
    }


def evaluate_builder_configurations() -> dict[str, object]:
    """Evaluate safe and boundary cases without running CLEO at runtime."""

    immediate = _parameters(0.0, 1.0)
    one_period = _parameters(0.5, 1.5)
    two_period = _parameters(1.0, 1.5)
    cases = (
        ("immediate_safe", context_for(immediate), (AttackerAction.FORCE_PRIMARY_ON,)),
        (
            "immediate_t1_margin_boundary",
            context_for(immediate, PlantState(x1=10.5, x2=6.0)),
            (AttackerAction.FORCE_PRIMARY_ON,),
        ),
        (
            "one_period_safe_reviewed",
            context_for(one_period),
            (AttackerAction.FORCE_PRIMARY_ON,),
        ),
        (
            "one_period_t1_margin_boundary",
            context_for(one_period, PlantState(x1=9.8, x2=6.0)),
            (AttackerAction.FORCE_PRIMARY_OFF,),
        ),
        (
            "two_period_safe",
            context_for(two_period),
            (AttackerAction.FORCE_PRIMARY_OFF, AttackerAction.FORCE_PRIMARY_ON),
        ),
        (
            "two_period_t2_margin_boundary",
            context_for(two_period, PlantState(x1=7.0, x2=8.8)),
            (AttackerAction.FORCE_PRIMARY_ON, AttackerAction.FORCE_PRIMARY_ON),
        ),
    )
    return {
        "scope": (
            "Builder construction and deterministic simulation are reported separately from reviewed "
            "certificate coverage. The reviewed one-period certificate is exact-schedule specific."
        ),
        "offline_proof_note": (
            "This evaluation never invokes CLEO. Runtime 1T authorization uses only the reviewed local "
            "provenance manifest, never a proof attempt or simulation result."
        ),
        "cases": {name: _case(name, context, schedule) for name, context, schedule in cases},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate builder-generated recovery configurations.")
    parser.add_argument(
        "--output", type=Path, default=Path("recovery_experiment/results/recovery-model-builder-evaluation.json")
    )
    args = parser.parse_args()
    report = evaluate_builder_configurations()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
