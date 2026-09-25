"""Symbolic state-dependent theorem for a flowing trusted-backup takeover."""

from __future__ import annotations

from dataclasses import dataclass


STATE_DEPENDENT_MODEL_ID = "state-dependent-flowing-takeover-v1"
STATE_DEPENDENT_POLICY_ID = "trusted-flowing-backup-takeover-v1"
STATE_DEPENDENT_PLANT_MODEL_ID = "state-dependent-two-tank-v1"


@dataclass(frozen=True)
class StateDependentFormalModel:
    model_id: str
    envelope_text: str
    certified_conditions: tuple[str, ...]


def render_state_dependent_recovery_envelope() -> StateDependentFormalModel:
    """Render the symbolic theorem without binding it to one runtime context."""

    text = '''envelope "State-dependent flowing trusted backup takeover recovery"

Guideline
    Offline theorem for a fixed takeover policy with continued startup inflow and downstream withdrawal.
    Stored water serves demand during startup; P2 restores the transfer path by TransferDeadline.

Definitions
    Definitions
        Bool safe(Real x1, Real x2) <-> (L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2);
    End.

    ProgramVariables
        Real x1; Real x2;
        Real L1; Real H1; Real L2; Real H2;
        Real p1; Real p2; Real isolated;
        Real qin; Real qout; Real demand; Real qprimary; Real qbackup; Real qmin;
        Real q1; Real q2; Real qdelivered;
        Real startupInflow; Real startupWithdrawal;
        Real startupClock; Real transferClock; Real operationClock;
        Real StartupDelay; Real TransferDeadline; Real T;
        Real interventionBudget; Real isolationCost; Real backupCost;
    End.

precondition
    L1 < H1 & L2 < H2
    & L1 >= 0 & L2 >= 0
    & L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
    & startupInflow >= 0 & startupWithdrawal >= qmin & qmin > 0
    & qprimary >= 0 & qbackup >= qmin
    & StartupDelay > 0 & TransferDeadline > 0 & StartupDelay <= TransferDeadline & T > 0
    & x1 + startupInflow * StartupDelay <= H1
    & x2 - startupWithdrawal * StartupDelay >= L2
    & isolationCost >= 0 & backupCost >= 0
    & interventionBudget >= isolationCost + backupCost

postcondition
    L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
    & isolated = 1 & p2 = 1
    & q1 = 0 & q1 = (1-isolated) * p1 * qprimary
    & q2 = qbackup & q2 = p2 * qbackup
    & qin = qbackup & demand = qbackup & qout = demand
    & qdelivered = qout & qdelivered >= qmin
    & startupClock = StartupDelay
    & transferClock = StartupDelay & transferClock <= TransferDeadline
    & operationClock = T
    & interventionBudget >= 0

game
    {
        {
            { p1 := 0; }
            ++
            { p1 := 1; }
        }^@;
        isolated := 1;
        p2 := 0;
        qin := startupInflow;
        demand := startupWithdrawal;
        qout := demand;
        q1 := 0;
        q2 := p2 * qbackup;
        qdelivered := qout;
        ? qdelivered >= qmin;
        startupClock := 0;
        transferClock := 0;
        startup_ode: {
            x1' = qin - q1 - q2,
            x2' = q1 + q2 - qout,
            startupClock' = 1,
            transferClock' = 1
            & L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
            & qdelivered >= qmin
            & startupClock <= StartupDelay & transferClock <= TransferDeadline
        };
        ? startupClock >= StartupDelay;
        ? transferClock <= TransferDeadline;
        {
            { p1 := 0; }
            ++
            { p1 := 1; }
        }^@;
        isolated := 1;
        p2 := 1;
        qin := qbackup;
        demand := qbackup;
        qout := demand;
        q1 := 0;
        q2 := p2 * qbackup;
        qdelivered := qout;
        interventionBudget := interventionBudget - (isolationCost + backupCost);
        ? qdelivered >= qmin;
        operationClock := 0;
        operation_ode: {
            x1' = qin - q1 - q2,
            x2' = q1 + q2 - qout,
            transferClock' = 0,
            operationClock' = 1
            & L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
            & qdelivered >= qmin & operationClock <= T
        };
        ? operationClock >= T;
    }
'''
    return StateDependentFormalModel(
        model_id=STATE_DEPENDENT_MODEL_ID,
        envelope_text=text,
        certified_conditions=(
            "L1 <= x1 <= H1 and L2 <= x2 <= H2 with L1,L2 >= 0",
            "startupInflow >= 0 and startupWithdrawal >= qmin > 0",
            "x1 + startupInflow*StartupDelay <= H1",
            "x2 - startupWithdrawal*StartupDelay >= L2",
            "qbackup >= qmin, 0 < StartupDelay <= TransferDeadline, and T > 0",
            "immediate effective trusted isolation; post-takeover qin = demand = qout = qbackup",
            "nonnegative action costs and budget covering isolation plus backup activation",
        ),
    )
