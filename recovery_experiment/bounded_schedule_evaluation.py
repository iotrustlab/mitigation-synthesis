"""Reproducible construction, proof-record, and simulation matrix for schedules."""

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
from .recovery_model_builder import BoundedIsolationSchedule, PhaseKind, build_recovery_problem
from .recovery_selection import incident_from_context, select_recovery_policy
from .scenarios import context_for


_ROOT = Path(__file__).resolve().parent


def _parameters(schedule: BoundedIsolationSchedule) -> PlantParameters:
    return replace(
        PlantParameters(),
        control_period=schedule.control_period,
        isolation_delay=schedule.isolation_delay,
        backup_startup_delay=schedule.startup_delay,
        transfer_recovery_deadline=schedule.startup_delay,
    )


def _margins(context) -> dict[str, float]:
    p, s = context.plant, context.current_state
    return {
        "t1_upper_startup": p.high_t1 - (s.x1 + p.startup_inflow_rate * p.backup_startup_delay),
        "t1_lower_primary_on_delay": s.x1 + (p.startup_inflow_rate - p.primary_capacity) * p.isolation_delay - p.low_t1,
        "t2_lower_startup": s.x2 - p.startup_withdrawal_rate * p.backup_startup_delay - p.low_t2,
        "t2_upper_primary_on_delay": p.high_t2 - (s.x2 + (p.primary_capacity - p.startup_withdrawal_rate) * p.isolation_delay),
    }


def _recorded_proof(schedule: BoundedIsolationSchedule) -> dict[str, object]:
    if schedule.isolation_periods == 1 and schedule.startup_periods == 3:
        path = _ROOT / "proof_records" / "intermediate_delay_1t" / "intermediate_delay_verification.json"
    elif schedule.isolation_periods == 3 and schedule.startup_periods in {4, 5}:
        path = _ROOT / "proof_records" / f"bounded_{schedule.isolation_periods}t{schedule.startup_periods}" / "bounded_delay_verification.json"
    else:
        return {"status": "REVIEWED_EXISTING_ARTIFACT" if schedule.isolation_periods in {0, 2} else "NOT_RECORDED"}
    try:
        proof = json.loads(path.read_text())
    except OSError:
        return {"status": "NOT_RECORDED", "record_path": str(path.relative_to(_ROOT))}
    return {
        "status": proof["status"],
        "elapsed_seconds": proof["elapsed_seconds"],
        "obligations": [
            {"game_id": item["game_id"], "kind": item["kind"], "profile": item["profile"], "passed": item["passed"]}
            for item in proof["obligations"]
        ],
        "record_path": str(path.relative_to(_ROOT)),
    }


def _simulate(
    context,
    schedule: BoundedIsolationSchedule,
    attacker_action: AttackerAction,
) -> dict[str, object]:
    if schedule.isolation_periods == 0:
        attacker = ScheduledPrimaryAttacker((attacker_action,))
        defender = TrustedFlowingBackupTakeoverPolicy()
        strategy = "trusted_flowing_backup_takeover"
    else:
        attacker = ScheduledPrimaryAttacker(
            tuple(attacker_action for _ in range(schedule.isolation_periods))
        )
        defender = TrustedDelayedIsolationFlowingBackupTakeoverPolicy()
        strategy = "trusted_delayed_isolation_flowing_backup_takeover"
    result = run_scenario("bounded_schedule_evaluation", context.plant, attacker, defender, initial_state=context.current_state)
    cost = calculate_cost(result, strategy, context.recovery_cost_parameters, service_target=context.plant.downstream_demand)
    return {
        "safe": result.safe,
        "continuous_minimum_service": all(row.q_delivered >= context.plant.min_service_flow for row in result.records),
        "recovery_established_at": result.final_state.recovery_established_at,
        "cost": cost.as_dict(),
    }


def _case(
    name: str,
    schedule: BoundedIsolationSchedule,
    state: PlantState,
    attacker_action: AttackerAction = AttackerAction.FORCE_PRIMARY_ON,
) -> dict[str, object]:
    started = perf_counter()
    context = context_for(_parameters(schedule), state)
    generated = build_recovery_problem(context)
    assessment = assess_incident_formal_problem(context)
    attacker_schedule = (
        None
        if schedule.isolation_periods == 0
        else tuple(attacker_action for _ in range(schedule.isolation_periods))
    )
    selection = select_recovery_policy(
        incident_from_context(context, require_continuous_delivery=True, attacker_schedule=attacker_schedule)
    )
    return {
        "name": name,
        "schedule": schedule.as_dict(),
        "context": context.as_dict(),
        "phase_summary": {
            "phase_count": len(generated.phases),
            "attacker_command_opportunities": sum(phase.kind is PhaseKind.ATTACKER_COMMAND for phase in generated.phases),
            "attacker_effective_intervals": sum(
                phase.kind is PhaseKind.ISOLATION_PENDING_EVOLUTION for phase in generated.phases
            ),
            "phase_kinds": [phase.kind.value for phase in generated.phases],
            "isolation_effective_time": context.plant.isolation_delay,
            "backup_available_time": context.plant.backup_startup_delay,
        },
        "derived_numeric_margins": _margins(context),
        "formal_assessment": assessment.as_dict(),
        "recorded_proof": _recorded_proof(schedule),
        "selection": selection.as_dict(),
        "simulation": _simulate(context, schedule, attacker_action),
        "local_construction_and_checking_latency_ms": (perf_counter() - started) * 1_000,
    }


def evaluate_bounded_schedules() -> dict[str, object]:
    """Compare reviewed and review-required schedules without running CLEO."""

    schedules = {
        "immediate_0t2t": BoundedIsolationSchedule(0.5, 0, 2),
        "reviewed_1t3t": BoundedIsolationSchedule(0.5, 1, 3),
        "reviewed_2t3t": BoundedIsolationSchedule(0.5, 2, 3),
        "generated_3t4t": BoundedIsolationSchedule(0.5, 3, 4),
        "generated_3t5t": BoundedIsolationSchedule(0.5, 3, 5),
    }
    return {
        "scope": (
            "Construction, reviewed certificate coverage, recorded offline proofs, and deterministic simulation are "
            "reported separately. A recorded CLEO proof does not authorize a schedule without reviewed provenance."
        ),
        "cases": {
            "0t2t_safe": _case("0t2t_safe", schedules["immediate_0t2t"], PlantState()),
            "1t3t_safe": _case("1t3t_safe", schedules["reviewed_1t3t"], PlantState()),
            "2t3t_safe": _case("2t3t_safe", schedules["reviewed_2t3t"], PlantState()),
            "3t4t_safe": _case("3t4t_safe", schedules["generated_3t4t"], PlantState()),
            "3t5t_safe": _case("3t5t_safe", schedules["generated_3t5t"], PlantState()),
            "2t3t_t2_margin_interior": _case(
                "2t3t_t2_margin_interior", schedules["reviewed_2t3t"], PlantState(x1=7.0, x2=8.6)
            ),
            "3t4t_t2_margin_failure": _case(
                "3t4t_t2_margin_failure", schedules["generated_3t4t"], PlantState(x1=7.0, x2=8.6)
            ),
            "3t5t_t2_lower_margin_failure": _case(
                "3t5t_t2_lower_margin_failure",
                schedules["generated_3t5t"],
                PlantState(x1=7.0, x2=5.9),
                AttackerAction.FORCE_PRIMARY_OFF,
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate bounded recovery schedule construction.")
    parser.add_argument(
        "--output", type=Path, default=Path("recovery_experiment/results/bounded-schedule-evaluation.json")
    )
    args = parser.parse_args()
    report = evaluate_bounded_schedules()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
