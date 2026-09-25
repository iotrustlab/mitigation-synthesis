"""Concrete CLEO instantiation of the state-dependent flowing-takeover theorem."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .context import RecoveryContext
from .formal import FormalReadiness, FormalStatus, _num
from .state_dependent_formal import (
    STATE_DEPENDENT_PLANT_MODEL_ID,
    STATE_DEPENDENT_POLICY_ID,
    render_state_dependent_recovery_envelope,
)


@dataclass(frozen=True)
class StateDependentFormalInstance:
    context: RecoveryContext
    envelope_text: str
    mapping: dict[str, str]


def assess_state_dependent_readiness(context: RecoveryContext) -> FormalReadiness:
    """Classify whether one context can instantiate the proved model unchanged."""

    context.validate()
    plant, state = context.plant, context.current_state
    if context.plant_model_id != STATE_DEPENDENT_PLANT_MODEL_ID:
        return FormalReadiness(FormalStatus.UNSUPPORTED_TEMPLATE, "wrong state-dependent plant identity")
    if context.recovery_policy_id != STATE_DEPENDENT_POLICY_ID:
        return FormalReadiness(FormalStatus.UNSUPPORTED_TEMPLATE, "wrong flowing-takeover policy identity")
    if plant.low_t1 < 0 or plant.low_t2 < 0:
        return FormalReadiness(
            FormalStatus.UNSUPPORTED_TEMPLATE,
            "the theorem requires nonnegative tank lower bounds",
        )
    if plant.startup_withdrawal_rate < plant.min_service_flow or plant.min_service_flow <= 0:
        return FormalReadiness(
            FormalStatus.REJECTED_SERVICE,
            "startup withdrawal must meet the positive continuous-service minimum",
        )
    if plant.backup_capacity < plant.min_service_flow:
        return FormalReadiness(
            FormalStatus.REJECTED_CAPACITY,
            "backup capacity is below the mandatory post-takeover delivered flow",
        )
    if plant.backup_startup_delay <= 0 or plant.transfer_recovery_deadline <= 0:
        return FormalReadiness(
            FormalStatus.UNSUPPORTED_TEMPLATE,
            "the theorem models a positive startup interval and transfer deadline",
        )
    if plant.backup_startup_delay > plant.transfer_recovery_deadline:
        return FormalReadiness(
            FormalStatus.REJECTED_DEADLINE,
            "the exact startup delay exceeds the transfer recovery deadline",
        )
    if not math.isclose(
        plant.backup_startup_delay / plant.control_period,
        round(plant.backup_startup_delay / plant.control_period),
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        return FormalReadiness(
            FormalStatus.UNSUPPORTED_TEMPLATE,
            "startup delay must align to the simulator control grid for this concrete trace theorem",
        )
    if plant.isolation_delay != 0:
        return FormalReadiness(
            FormalStatus.UNSUPPORTED_TEMPLATE,
            "the theorem requires immediate effective trusted isolation",
        )
    if (
        plant.backup_capacity != plant.upstream_nominal
        or plant.backup_capacity != plant.downstream_demand
    ):
        return FormalReadiness(
            FormalStatus.UNSUPPORTED_TEMPLATE,
            "the theorem requires balanced post-takeover inflow, withdrawal, and backup flow",
        )
    if state.x1 + plant.startup_inflow_rate * plant.backup_startup_delay > plant.high_t1:
        return FormalReadiness(
            FormalStatus.UNSUPPORTED_TEMPLATE,
            "the initial T1 level lacks the required startup overflow margin",
        )
    if state.x2 - plant.startup_withdrawal_rate * plant.backup_startup_delay < plant.low_t2:
        return FormalReadiness(
            FormalStatus.UNSUPPORTED_TEMPLATE,
            "the initial T2 level lacks the required startup depletion margin",
        )
    assurance = context.takeover_assurance
    if assurance.intervention_budget < assurance.isolation_cost + assurance.backup_activation_cost:
        return FormalReadiness(
            FormalStatus.UNSUPPORTED_TEMPLATE,
            "the intervention budget cannot pay the trusted recovery actions",
        )
    return FormalReadiness(FormalStatus.NOT_RUN, "eligible for concrete state-dependent CLEO verification")


def _precondition(context: RecoveryContext, *, operation_duration: float | None = None) -> str:
    p, s, a = context.plant, context.current_state, context.takeover_assurance
    duration = p.control_period if operation_duration is None else operation_duration
    if duration <= 0:
        raise ValueError("mandatory operation duration must be positive")
    return f"""
L1 = {_num(p.low_t1)} & H1 = {_num(p.high_t1)}
& L2 = {_num(p.low_t2)} & H2 = {_num(p.high_t2)}
& x1 = {_num(s.x1)} & x2 = {_num(s.x2)}
& qprimary = {_num(p.primary_capacity)} & qbackup = {_num(p.backup_capacity)}
& qmin = {_num(p.min_service_flow)}
& startupInflow = {_num(p.startup_inflow_rate)}
& startupWithdrawal = {_num(p.startup_withdrawal_rate)}
& StartupDelay = {_num(p.backup_startup_delay)}
& TransferDeadline = {_num(p.transfer_recovery_deadline)} & T = {_num(duration)}
& isolationCost = {_num(a.isolation_cost)} & backupCost = {_num(a.backup_activation_cost)}
& interventionBudget = {_num(a.intervention_budget)}
& L1 < H1 & L2 < H2 & L1 >= 0 & L2 >= 0
& L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
& startupInflow >= 0 & startupWithdrawal >= qmin & qmin > 0
& qprimary >= 0 & qbackup >= qmin
& StartupDelay > 0 & TransferDeadline > 0 & StartupDelay <= TransferDeadline & T > 0
& x1 + startupInflow * StartupDelay <= H1
& x2 - startupWithdrawal * StartupDelay >= L2
& isolationCost >= 0 & backupCost >= 0
& interventionBudget >= isolationCost + backupCost
""".strip()


def _section(text: str) -> str:
    return "\n".join(f"    {line}" for line in text.splitlines())


def render_state_dependent_context_envelope(
    context: RecoveryContext, *, operation_duration: float | None = None
) -> StateDependentFormalInstance:
    """Instantiate the checked symbolic game only by replacing its precondition.

    ``operation_duration`` is used only by an offline finite-horizon check.  It
    leaves the legacy concrete baseline unchanged when omitted.
    """

    readiness = assess_state_dependent_readiness(context)
    if readiness.status is not FormalStatus.NOT_RUN:
        raise ValueError(f"cannot instantiate state-dependent theorem: {readiness.reason}")
    symbolic = render_state_dependent_recovery_envelope().envelope_text
    before, remainder = symbolic.split("\nprecondition\n", maxsplit=1)
    _, after = remainder.split("\n\npostcondition\n", maxsplit=1)
    text = f"{before}\nprecondition\n{_section(_precondition(context, operation_duration=operation_duration))}\n\npostcondition\n{after}"
    return StateDependentFormalInstance(
        context=context,
        envelope_text=text,
        mapping={
            "simulator.x1": "x1",
            "simulator.x2": "x2",
            "simulator.q_in": "qin = startupInflow during startup, qbackup after takeover",
            "simulator.q_out": "qout = demand = startupWithdrawal during startup",
            "simulator.q1": "q1 = (1-isolated) * p1 * qprimary",
            "simulator.q2": "q2 = p2 * qbackup",
            "simulator.q_delivered": "qdelivered = qout",
            "simulator.transfer_deadline": "TransferDeadline",
        },
    )
