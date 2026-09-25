"""Generate reproducible traces and compare the two scripted recovery policies."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .cost import calculate_cost
from .experiment import default_scenarios, run_scenario, write_trace
from .formal import FormalStatus, assess_takeover_readiness
from .policies import ConservativeRecoveryPolicy, PersistentPrimaryAttacker, TrustedBackupTakeoverPolicy
from .scenarios import named_contexts
from .verify_recovery import verify_context


def _conservative_status(result) -> tuple[FormalStatus, str]:
    if result.parameters.min_service_flow > 0:
        return (
            FormalStatus.REJECTED_SERVICE,
            "conservative hold deliberately supplies zero flow after the mandatory service deadline",
        )
    return FormalStatus.NOT_RUN, "no conservative formal template is implemented"


def _comparison_for_context(name: str, context, *, seed: int, verify: bool, output_dir: Path) -> dict[str, object]:
    parameters = context.plant
    attacker = PersistentPrimaryAttacker(active_until=parameters.horizon)
    conservative = run_scenario(
        "conservative_recovery", parameters, attacker, ConservativeRecoveryPolicy(), seed=seed
    )
    takeover = run_scenario(
        "trusted_backup_takeover", parameters, attacker, TrustedBackupTakeoverPolicy(), seed=seed
    )
    conservative_status, conservative_reason = _conservative_status(conservative)
    readiness = assess_takeover_readiness(context)
    takeover_status, takeover_reason = readiness.status, readiness.reason
    formal_details: dict[str, object] = {}
    if verify and readiness.status is FormalStatus.NOT_RUN:
        verification = verify_context(context, output_dir=output_dir / name / "formal")
        takeover_status, takeover_reason = verification.status, verification.reason
        formal_details = verification.as_dict()
    candidates = {
        "conservative_recovery": {
            "formal_status": conservative_status.value,
            "formal_reason": conservative_reason,
            "simulation_safe": conservative.safe,
            "simulation_service_after_deadline": conservative.service_satisfied_after_deadline,
            "cost": calculate_cost(
                conservative, "conservative_recovery", context.recovery_cost_parameters
            ).as_dict(),
        },
        "trusted_backup_takeover": {
            "formal_status": takeover_status.value,
            "formal_reason": takeover_reason,
            "simulation_safe": takeover.safe,
            "simulation_service_after_deadline": takeover.service_satisfied_after_deadline,
            "cost": calculate_cost(
                takeover, "trusted_backup_takeover", context.recovery_cost_parameters
            ).as_dict(),
        },
    }
    verified = [
        (strategy, entry["cost"]["total"])
        for strategy, entry in candidates.items()
        if entry["formal_status"] == FormalStatus.VERIFIED.value
        and entry["simulation_safe"]
        and entry["simulation_service_after_deadline"]
    ]
    selection = min(verified, key=lambda item: item[1])[0] if verified else None
    return {
        "context": name,
        "seed": seed,
        "candidates": candidates,
        "formal_details": formal_details,
        "selected_verified_strategy": selection,
        "selection_status": (
            FormalStatus.VERIFIED.value
            if selection
            else FormalStatus.NO_VERIFIED_SERVICE_CANDIDATE.value
        ),
        "selection_note": (
            "costs are compared only after formal verification and service qualification"
            if selection
            else "no formally verified, service-qualified candidate; escalate rather than execute an unverified strategy"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run trace-driven recovery experiments.")
    parser.add_argument("--output-dir", type=Path, default=Path("recovery_experiment/results"))
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="invoke CLEO for contexts inside the supported formal model domain",
    )
    parser.add_argument(
        "--suite",
        action="store_true",
        help="also run the four non-baseline synthetic contexts",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for name, result in default_scenarios(seed=args.seed).items():
        write_trace(result, args.output_dir / "traces" / f"{name}.json")
        write_trace(result, args.output_dir / "traces" / f"{name}.csv", fmt="csv")

    contexts = named_contexts()
    selected_contexts = contexts if args.suite else {"baseline_feasible": contexts["baseline_feasible"]}
    comparison = {
        name: _comparison_for_context(
            name, context, seed=args.seed, verify=args.verify, output_dir=args.output_dir
        )
        for name, context in selected_contexts.items()
    }
    (args.output_dir / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")
    print(json.dumps(comparison, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
