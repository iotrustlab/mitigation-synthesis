"""Named synthetic contexts used for controlled, reproducible experiment sweeps."""

from __future__ import annotations

from dataclasses import replace

from .context import RecoveryContext
from .model import PlantParameters, PlantState, TwoTankPlant


def context_for(parameters: PlantParameters, state: PlantState | None = None) -> RecoveryContext:
    context = RecoveryContext.from_plant(TwoTankPlant(parameters, state))
    context.validate()
    return context


def named_contexts() -> dict[str, RecoveryContext]:
    """Contexts distinguish simulation outcomes from the scope of the first proof."""

    baseline = PlantParameters()
    insufficient_capacity = replace(baseline, backup_capacity=1.0)
    delayed_inadmissible = replace(baseline, backup_startup_delay=2.0)
    # Conservative control holds both levels but loses service after its deadline.
    conservative_service_loss = baseline
    # Neither policy can meet service: takeover is too small and shutdown is zero-flow.
    neither = replace(baseline, backup_capacity=0.8)
    return {
        "baseline_feasible": context_for(baseline),
        "insufficient_backup_capacity": context_for(insufficient_capacity),
        "startup_deadline_inadmissible": context_for(delayed_inadmissible),
        "conservative_safe_service_loss": context_for(conservative_service_loss),
        "neither_candidate_verified": context_for(neither),
    }
