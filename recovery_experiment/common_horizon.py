"""Bind the existing finite symbolic theorems to one evaluation horizon.

The canonical recovery theorems deliberately use a symbolic, strictly positive
operation duration ``T``.  This module does not alter those theorems.  It makes
the finite instantiation used by policy selection explicit: the exact startup
phase consumes ``StartupDelay`` and the mandatory operation phase consumes
``T = evaluation_horizon - StartupDelay``.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from .context import RecoveryContext
from .formal import _num
from .model import PlantParameters
from .parameterized_formal import render_parameterized_recovery_envelope


@dataclass(frozen=True)
class CommonFormalHorizon:
    """One exact finite recovery timeline, measured from attack response start."""

    startup_duration: float
    post_takeover_operation_duration: float
    total_duration: float

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


def derive_common_formal_horizon(
    plant: PlantParameters, evaluation_horizon: float
) -> CommonFormalHorizon:
    """Instantiate the existing symbolic ``T`` without introducing a loop.

    The original games sequence two exact, mandatory ODE phases.  Thus their
    finite elapsed time is ``StartupDelay + T``.  ``T`` must be positive, so an
    evaluation horizon at or before the startup boundary is not certified by
    this contract.
    """

    values = (plant.backup_startup_delay, evaluation_horizon)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("formal-horizon values must be finite")
    operation_duration = evaluation_horizon - plant.backup_startup_delay
    if plant.backup_startup_delay <= 0 or operation_duration <= 0:
        raise ValueError(
            "common formal horizon requires a positive startup phase and positive mandatory operation phase"
        )
    return CommonFormalHorizon(
        startup_duration=plant.backup_startup_delay,
        post_takeover_operation_duration=operation_duration,
        total_duration=evaluation_horizon,
    )


def render_controlled_hold_horizon_envelope(
    context: RecoveryContext, horizon: CommonFormalHorizon
) -> str:
    """Concretely instantiate the unchanged controlled-hold symbolic theorem.

    This is an offline verification helper.  It substitutes a concrete context
    only in the precondition and keeps the canonical game and postcondition
    byte-for-byte sourced from ``parameterized_formal.py``.
    """

    p, s, a = context.plant, context.current_state, context.takeover_assurance
    precondition = f"""
L1 = {_num(p.low_t1)} & H1 = {_num(p.high_t1)}
& L2 = {_num(p.low_t2)} & H2 = {_num(p.high_t2)}
& x1 = {_num(s.x1)} & x2 = {_num(s.x2)}
& qprimary = {_num(p.primary_capacity)} & qbackup = {_num(p.backup_capacity)}
& qmin = {_num(p.min_service_flow)}
& StartupDelay = {_num(horizon.startup_duration)}
& RecoveryDeadline = {_num(p.service_deadline)}
& T = {_num(horizon.post_takeover_operation_duration)}
& isolationCost = {_num(a.isolation_cost)} & backupCost = {_num(a.backup_activation_cost)}
& interventionBudget = {_num(a.intervention_budget)}
& L1 < H1 & L2 < H2 & L1 >= 0 & L2 >= 0
& L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
& qprimary >= 0 & qbackup >= qmin & qmin > 0
& StartupDelay > 0 & T > 0 & StartupDelay <= RecoveryDeadline
& isolationCost >= 0 & backupCost >= 0
& interventionBudget >= isolationCost + backupCost
""".strip()
    symbolic = render_parameterized_recovery_envelope().envelope_text
    before, remainder = symbolic.split("\nprecondition\n", maxsplit=1)
    _, after = remainder.split("\n\npostcondition\n", maxsplit=1)
    indented_precondition = "\n".join(f"    {line}" for line in precondition.splitlines())
    return f"{before}\nprecondition\n{indented_precondition}\n\npostcondition\n{after}"
