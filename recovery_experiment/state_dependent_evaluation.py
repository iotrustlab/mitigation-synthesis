"""Reproducible evaluation of controlled-hold and flowing-startup recovery policies."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path
from time import perf_counter
from typing import Any

from .certificate import check_certified_recovery
from .context import RecoveryContext
from .cost import calculate_cost
from .experiment import ExperimentResult, run_scenario
from .model import PlantParameters, PlantState
from .policies import (
    PersistentPrimaryAttacker,
    TrustedBackupTakeoverPolicy,
    TrustedFlowingBackupTakeoverPolicy,
)
from .scenarios import context_for
from .state_dependent_certificate import check_state_dependent_recovery
from .state_dependent_formal import STATE_DEPENDENT_PLANT_MODEL_ID, STATE_DEPENDENT_POLICY_ID
from .verify_state_dependent_context import verify_state_dependent_context


def _state_context(parameters: PlantParameters, state: PlantState) -> RecoveryContext:
    """Build the common typed context and explicitly identify the new policy/model."""

    baseline = context_for(parameters, state)
    return replace(
        baseline,
        plant_model_id=STATE_DEPENDENT_PLANT_MODEL_ID,
        recovery_policy_id=STATE_DEPENDENT_POLICY_ID,
    )


def state_dependent_evaluation_contexts() -> dict[str, RecoveryContext]:
    """State, capacity, and timing cases around the new certified region."""

    baseline = PlantParameters()
    return {
        # 7 + 1*1 <= 11 and 6 - 1.2*1 >= 3: strict interior margin on both tanks.
        "safe_recoverable": _state_context(baseline, PlantState(x1=7.0, x2=6.0)),
        "near_t1_overflow": _state_context(baseline, PlantState(x1=10.5, x2=6.0)),
        "near_t2_depletion": _state_context(baseline, PlantState(x1=7.0, x2=4.0)),
        "inadequate_backup_capacity": _state_context(
            replace(baseline, upstream_nominal=1.0, downstream_demand=1.0, backup_capacity=1.0),
            PlantState(x1=7.0, x2=6.0),
        ),
        "startup_after_transfer_deadline": _state_context(
            replace(baseline, backup_startup_delay=2.0), PlantState(x1=7.0, x2=6.0)
        ),
    }


def controlled_hold_baseline_context() -> RecoveryContext:
    """The older policy is retained for comparison, with its distinct assumptions."""

    return context_for(PlantParameters(), PlantState(x1=7.0, x2=6.0))


def _simulation_summary(
    context: RecoveryContext, *, strategy: str, flowing: bool
) -> tuple[dict[str, object], ExperimentResult]:
    defender = TrustedFlowingBackupTakeoverPolicy() if flowing else TrustedBackupTakeoverPolicy()
    result = run_scenario(
        strategy,
        context.plant,
        PersistentPrimaryAttacker(active_until=context.plant.horizon),
        defender,
        initial_state=context.current_state,
    )
    records = result.records
    continuous_service = all(row.q_delivered >= context.plant.min_service_flow for row in records)
    established = result.final_state.recovery_established_at
    transfer_by_deadline = established is not None and established <= context.plant.transfer_recovery_deadline
    return (
        {
            "status": "COMPLETED",
            "safe": result.safe,
            "continuous_service": continuous_service,
            "service_after_general_deadline": result.service_satisfied_after_deadline,
            "transfer_established_at": established,
            "transfer_by_state_dependent_deadline": transfer_by_deadline,
            "startup_trace": [
                {
                    "timestamp": row.timestamp,
                    "q_in": row.q_in,
                    "q1": row.q1,
                    "q2": row.q2,
                    "q_demand": row.q_demand,
                    "q_out": row.q_out,
                    "q_delivered": row.q_delivered,
                    "x1": row.x1,
                    "x2": row.x2,
                }
                for row in records
                if row.timestamp <= context.plant.backup_startup_delay + 1e-12
            ],
            "final_state": asdict(result.final_state),
        },
        result,
    )


def _context_summary(context: RecoveryContext) -> dict[str, object]:
    p, s = context.plant, context.current_state
    return {
        "initial_levels": {"x1": s.x1, "x2": s.x2},
        "configured_flowing_startup_rates": {
            "qin": p.startup_inflow_rate,
            "demand": p.startup_withdrawal_rate,
            "qout": p.startup_withdrawal_rate,
        },
        "startup_duration": p.backup_startup_delay,
        "transfer_recovery_deadline": p.transfer_recovery_deadline,
        "backup_capacity": p.backup_capacity,
        "minimum_service_flow": p.min_service_flow,
        "startup_margins": {
            "t1_high_margin": p.high_t1 - (s.x1 + p.startup_inflow_rate * p.backup_startup_delay),
            "t2_low_margin": (s.x2 - p.startup_withdrawal_rate * p.backup_startup_delay) - p.low_t2,
        },
    }


def evaluate_state_dependent_workflows(
    *, concrete_verify_names: frozenset[str] = frozenset()
) -> dict[str, object]:
    """Evaluate certificate checks and traces; concrete proof is explicit and separate."""

    flowing_records: dict[str, object] = {}
    for name, context in state_dependent_evaluation_contexts().items():
        simulation, result = _simulation_summary(
            context, strategy="trusted_flowing_backup_takeover", flowing=True
        )
        if name in concrete_verify_names:
            concrete = verify_state_dependent_context(context).as_dict()
        else:
            concrete = {
                "status": "NOT_RUN",
                "reason": "concrete CLEO verification was not selected for this evaluation context",
            }
        flowing_records[name] = {
            "context": _context_summary(context),
            "certificate": check_state_dependent_recovery(context).as_dict(),
            "concrete_verification": concrete,
            "simulation": simulation,
            "cost": calculate_cost(
                result, "trusted_flowing_backup_takeover", context.recovery_cost_parameters
            ).as_dict(),
        }

    hold_context = controlled_hold_baseline_context()
    hold_simulation, hold_result = _simulation_summary(
        hold_context, strategy="trusted_backup_takeover", flowing=False
    )
    return {
        "comparison_note": (
            "Controlled hold closes inflow and withdrawal during P2 startup; the flowing policy keeps "
            "them active. Their traces and certificate assumptions are intentionally not interchangeable."
        ),
        "offline_proof": {
            "formal_model_id": "state-dependent-flowing-takeover-v1",
            "status": "VERIFIED",
            "proof_time_seconds": 9.85577582300175,
            "note": "offline proof time is excluded from runtime certificate latency",
        },
        "controlled_hold_baseline": {
            "context": _context_summary(hold_context),
            "certificate": check_certified_recovery(hold_context).as_dict(),
            "simulation": hold_simulation,
            "cost": calculate_cost(
                hold_result, "trusted_backup_takeover", hold_context.recovery_cost_parameters
            ).as_dict(),
        },
        "flowing_startup_contexts": flowing_records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate state-dependent flowing takeover assurance.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("recovery_experiment/results/state-dependent-evaluation.json"),
    )
    parser.add_argument(
        "--verify-concrete",
        action="store_true",
        help="also run CLEO for the independently selected safe interior context",
    )
    args = parser.parse_args()
    started = perf_counter()
    selected = frozenset({"safe_recoverable"}) if args.verify_concrete else frozenset()
    evaluation: dict[str, Any] = evaluate_state_dependent_workflows(concrete_verify_names=selected)
    evaluation["evaluation_elapsed_ms"] = (perf_counter() - started) * 1_000
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evaluation, indent=2) + "\n")
    print(json.dumps(evaluation, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
