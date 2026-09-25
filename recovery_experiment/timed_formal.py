"""Concrete, explicitly timed takeover contract for the fixed recovery policy."""

from __future__ import annotations

from dataclasses import dataclass

from .context import RecoveryContext
from .formal import FormalReadiness, FormalStatus, _num


@dataclass(frozen=True)
class TimedFormalInstance:
    context: RecoveryContext
    envelope_text: str
    mapping: dict[str, str]


def assess_timed_takeover_readiness(context: RecoveryContext) -> FormalReadiness:
    """Classify only what the concrete timed theorem can establish."""

    context.validate()
    plant = context.plant
    if plant.backup_capacity < plant.min_service_flow:
        return FormalReadiness(
            FormalStatus.REJECTED_CAPACITY,
            "backup capacity is below the required actual delivered flow",
        )
    if plant.backup_startup_delay > plant.service_deadline:
        return FormalReadiness(
            FormalStatus.REJECTED_DEADLINE,
            "the exact configured startup delay exceeds the recovery deadline",
        )
    if plant.isolation_delay != 0:
        return FormalReadiness(
            FormalStatus.UNSUPPORTED_TEMPLATE,
            "the timed theorem assumes immediate effective trusted isolation",
        )
    if plant.low_t1 < 0 or plant.low_t2 < 0:
        return FormalReadiness(
            FormalStatus.UNSUPPORTED_TEMPLATE,
            "the timed theorem requires nonnegative tank lower bounds for its ODE domains",
        )
    if plant.backup_startup_delay <= 0 or plant.min_service_flow <= 0:
        return FormalReadiness(
            FormalStatus.UNSUPPORTED_TEMPLATE,
            "the timed theorem models a positive startup interval and a positive service minimum",
        )
    if plant.upstream_nominal != plant.downstream_demand:
        return FormalReadiness(
            FormalStatus.UNSUPPORTED_TEMPLATE,
            "the timed theorem assumes balanced post-takeover inflow and demand",
        )
    if plant.backup_capacity != plant.upstream_nominal:
        return FormalReadiness(
            FormalStatus.UNSUPPORTED_TEMPLATE,
            "the timed theorem assumes backup flow equals the balanced nominal flow",
        )
    return FormalReadiness(FormalStatus.NOT_RUN, "eligible for the concrete timed theorem")


def _precondition(context: RecoveryContext) -> str:
    p, s = context.plant, context.current_state
    return f"""
L1 = {_num(p.low_t1)} & H1 = {_num(p.high_t1)}
& L2 = {_num(p.low_t2)} & H2 = {_num(p.high_t2)}
& x1 = {_num(s.x1)} & x2 = {_num(s.x2)}
& qprimary = {_num(p.primary_capacity)} & qbackup = {_num(p.backup_capacity)}
& qmin = {_num(p.min_service_flow)}
& StartupDelay = {_num(p.backup_startup_delay)}
& RecoveryDeadline = {_num(p.service_deadline)}
& T = {_num(p.control_period)}
& isolationCost = 1 & backupCost = 1 & interventionBudget = 2
& L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
& L1 >= 0 & L2 >= 0
& qprimary >= 0 & qbackup >= qmin & qmin > 0
& StartupDelay > 0 & T > 0 & StartupDelay <= RecoveryDeadline
& p1 = {1 if s.p1_command else 0} & p2 = {1 if s.p2_command else 0}
& isolated = {1 if s.primary_path_isolated else 0}
""".strip()


def _section(text: str) -> str:
    return "\n".join(f"    {line}" for line in text.splitlines())


def render_timed_recovery_envelope(context: RecoveryContext) -> TimedFormalInstance:
    """Render the one fixed policy without caller-supplied game fragments."""

    readiness = assess_timed_takeover_readiness(context)
    if readiness.status is not FormalStatus.NOT_RUN:
        raise ValueError(f"cannot instantiate timed recovery theorem: {readiness.reason}")

    text = f'''envelope "Timed trusted backup takeover recovery"

Guideline
    Fixed exact-duration takeover: isolate P1, wait StartupDelay, activate P2 by RecoveryDeadline,
    and execute one mandatory post-takeover operating interval with actual delivered service.

Definitions
    Definitions
        Bool safe(Real x1, Real x2) <-> (L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2);
    End.

    ProgramVariables
        Real x1; Real x2;
        Real L1; Real H1; Real L2; Real H2;
        Real p1; Real p2; Real isolated;
        Real qin; Real qd; Real qprimary; Real qbackup; Real qmin;
        Real q1; Real q2; Real qdelivered;
        Real startupClock; Real recoveryClock; Real operationClock;
        Real StartupDelay; Real RecoveryDeadline; Real T;
        Real interventionBudget; Real isolationCost; Real backupCost;
    End.

precondition
{_section(_precondition(context))}

postcondition
    L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
    & isolated = 1 & p2 = 1
    & q1 = 0 & q1 = (1-isolated) * p1 * qprimary
    & q2 = qbackup & q2 = p2 * qbackup & qd = qbackup & qin = qbackup
    & qdelivered = q2 & qdelivered = qd & qdelivered >= qmin
    & startupClock = StartupDelay
    & recoveryClock = StartupDelay & recoveryClock <= RecoveryDeadline
    & operationClock = T
    & interventionBudget >= 0

game
    {{
        {{
            {{ p1 := 0; }}
            ++
            {{ p1 := 1; }}
        }}^@;
        isolated := 1;
        p2 := 0;
        qin := 0;
        qd := 0;
        q1 := 0;
        q2 := p2 * qbackup;
        qdelivered := 0;
        startupClock := 0;
        recoveryClock := 0;
        startup_ode: {{
            x1' = qin - q1 - q2,
            x2' = q1 + q2 - qd,
            startupClock' = 1,
            recoveryClock' = 1
            & x1 >= 0 & x2 >= 0
            & startupClock <= StartupDelay & recoveryClock <= RecoveryDeadline
        }};
        ? startupClock >= StartupDelay;
        ? recoveryClock <= RecoveryDeadline;
        {{
            {{ p1 := 0; }}
            ++
            {{ p1 := 1; }}
        }}^@;
        isolated := 1;
        p2 := 1;
        qin := qbackup;
        qd := qbackup;
        q1 := 0;
        q2 := p2 * qbackup;
        qdelivered := q2;
        interventionBudget := interventionBudget - (isolationCost + backupCost);
        ? qdelivered >= qmin;
        operationClock := 0;
        operation_ode: {{
            x1' = qin - q1 - q2,
            x2' = q1 + q2 - qd,
            recoveryClock' = 0,
            operationClock' = 1
            & x1 >= 0 & x2 >= 0 & operationClock <= T
        }};
        ? operationClock >= T;
    }}
'''
    return TimedFormalInstance(
        context=context,
        envelope_text=text,
        mapping={
            "simulator.x1": "x1",
            "simulator.x2": "x2",
            "simulator.P1_command": "p1",
            "simulator.P2_command": "p2",
            "simulator.primary_path_isolated": "isolated",
            "simulator.q1": "q1 = (1-isolated) * p1 * qprimary",
            "simulator.q2": "q2 = p2 * qbackup",
            "simulator.q_delivered": "qdelivered = q2 = qd",
            "simulator.service_deadline": "RecoveryDeadline",
        },
    )
