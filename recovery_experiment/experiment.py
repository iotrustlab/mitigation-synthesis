"""Scenario execution, trace serialization, and transparent finite-horizon costs."""

from __future__ import annotations

import csv
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from .context import RecoveryContext
from .model import AttackerAction, DefenderAction, PlantParameters, PlantState, StepRecord, TwoTankPlant
from .policies import (
    ConservativeRecoveryPolicy,
    NoRecoveryPolicy,
    PersistentPrimaryAttacker,
    TrustedBackupTakeoverPolicy,
)


class AttackerPolicy(Protocol):
    def select(self, state: PlantState) -> AttackerAction: ...


class DefenderPolicy(Protocol):
    def select(self, state: PlantState) -> DefenderAction: ...


@dataclass(frozen=True)
class ExperimentResult:
    scenario: str
    seed: int
    parameters: PlantParameters
    records: tuple[StepRecord, ...]
    final_state: PlantState
    context: RecoveryContext

    @property
    def safe(self) -> bool:
        return all(record.safety_status == "safe" for record in self.records)

    @property
    def service_satisfied_after_deadline(self) -> bool:
        required = [record for record in self.records if record.service_status != "not_yet_required"]
        return bool(required) and all(record.service_status == "satisfied" for record in required)

    def metadata(self) -> dict[str, object]:
        return {
            "scenario": self.scenario,
            "seed": self.seed,
            "parameters": self.parameters.as_dict(),
            "event_order": [
                "observe",
                "attacker_action",
                "defender_action",
                "zero_delay_trusted_transition",
                "flow_calculation",
                "forward_euler_physical_evolution",
                "monitor_evaluation",
                "delayed_transition_clock_advance",
            ],
            "integration": "forward Euler; one integration step per control period",
            "context": self.context.as_dict(),
        }


def run_scenario(
    scenario: str,
    parameters: PlantParameters,
    attacker: AttackerPolicy,
    defender: DefenderPolicy,
    *,
    seed: int = 7,
    initial_state: PlantState | None = None,
) -> ExperimentResult:
    """Run a deterministic trace; the seed is stored even though policies are scripted."""

    random.Random(seed)  # Reserve deterministic entropy for future explicit stochastic models.
    plant = TwoTankPlant(parameters, initial_state)
    # The recovery context represents the observed state at recovery decision time,
    # not an arbitrary final state that may already have become unsafe.
    context = RecoveryContext.from_plant(plant)
    context.validate()
    records: list[StepRecord] = []
    while plant.state.time < parameters.horizon - 1e-12:
        remaining = parameters.horizon - plant.state.time
        dt = min(parameters.control_period, remaining)
        records.append(plant.step(attacker.select(plant.state), defender.select(plant.state), dt))
    return ExperimentResult(
        scenario=scenario,
        seed=seed,
        parameters=parameters,
        records=tuple(records),
        final_state=plant.state.copy(),
        context=context,
    )


def default_scenarios(parameters: PlantParameters | None = None, *, seed: int = 7) -> dict[str, ExperimentResult]:
    """The four required trace categories for the baseline synthetic configuration."""

    parameters = parameters or PlantParameters()
    attack = PersistentPrimaryAttacker(active_until=parameters.horizon)
    return {
        "normal_operation": run_scenario(
            "normal_operation",
            parameters,
            PersistentPrimaryAttacker(AttackerAction.NOOP, active_until=0.0),
            NoRecoveryPolicy(),
            seed=seed,
        ),
        "primary_compromise_no_recovery": run_scenario(
            "primary_compromise_no_recovery", parameters, attack, NoRecoveryPolicy(), seed=seed
        ),
        "conservative_recovery": run_scenario(
            "conservative_recovery", parameters, attack, ConservativeRecoveryPolicy(), seed=seed
        ),
        "trusted_backup_takeover": run_scenario(
            "trusted_backup_takeover", parameters, attack, TrustedBackupTakeoverPolicy(), seed=seed
        ),
    }


def write_trace(result: ExperimentResult, destination: Path, fmt: str = "json") -> Path:
    """Write complete metadata with JSON, or flat trace rows with CSV."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    rows = [record.as_dict() for record in result.records]
    if fmt == "json":
        destination.write_text(json.dumps({"metadata": result.metadata(), "records": rows}, indent=2) + "\n")
    elif fmt == "csv":
        if not rows:
            raise ValueError("cannot write an empty trace")
        with destination.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    else:
        raise ValueError("fmt must be 'json' or 'csv'")
    return destination


def result_as_dict(result: ExperimentResult) -> dict[str, object]:
    return {
        "scenario": result.scenario,
        "seed": result.seed,
        "safe_in_simulation": result.safe,
        "service_satisfied_after_deadline_in_simulation": result.service_satisfied_after_deadline,
        "final_state": asdict(result.final_state),
    }
