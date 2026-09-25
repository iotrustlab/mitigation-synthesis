"""Parameterized delayed-isolation theorem for the flowing backup policy.

P2 startup and trusted isolation start concurrently.  The first proof-supported
timing family has two attacker control intervals before physical isolation and
one remaining backup-start interval after isolation.  The explicit phases avoid
claiming repeated attacker changes that the game does not encode.
"""

from __future__ import annotations

from dataclasses import dataclass


DELAYED_ISOLATION_MODEL_ID = "delayed-isolation-flowing-takeover-v1"
DELAYED_ISOLATION_POLICY_ID = "trusted-delayed-isolation-flowing-backup-takeover-v1"
DELAYED_ISOLATION_PLANT_MODEL_ID = "delayed-isolation-state-dependent-two-tank-v1"


@dataclass(frozen=True)
class DelayedIsolationFormalModel:
    model_id: str
    envelope_text: str
    certified_conditions: tuple[str, ...]


def render_delayed_isolation_recovery_envelope() -> DelayedIsolationFormalModel:
    """Render the separate symbolic delayed-isolation recovery theorem.

    ``ControlPeriod`` is the exact attacker command interval.  The explicit
    equalities ``IsolationDelay = 2*ControlPeriod`` and
    ``StartupDelay = 3*ControlPeriod`` are deliberately conservative: they
    make two pre-isolation Demon choices and the remaining startup phase
    explicit without using a zero-or-more loop.
    """

    text = '''envelope "Delayed-isolation flowing trusted backup takeover recovery"

Guideline
    Offline theorem for an attacker that can choose P1 at two control boundaries before
    physical isolation becomes effective. P2 startup begins concurrently with isolation.

Definitions
    Definitions
        Bool safe(Real x1, Real x2) <-> (L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2);
    End.

    ProgramVariables
        Real x1; Real x2;
        Real L1; Real H1; Real L2; Real H2;
        Real p1; Real p2; Real p2Command; Real isolated; Real isolationCommanded;
        Real qin; Real qout; Real demand; Real qprimary; Real qbackup; Real qmin;
        Real q1; Real q2; Real qdelivered;
        Real startupInflow; Real startupWithdrawal;
        Real isolationClock; Real startupClock; Real transferClock; Real operationClock;
        Real ControlPeriod; Real IsolationDelay; Real StartupDelay; Real TransferDeadline; Real T;
        Real interventionBudget; Real isolationCost; Real backupCost;
    End.

precondition
    L1 < H1 & L2 < H2
    & L1 >= 0 & L2 >= 0
    & L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
    & startupInflow >= 0 & startupWithdrawal >= qmin & qmin > 0
    & qprimary >= startupInflow & qprimary >= startupWithdrawal & qbackup >= qmin
    & ControlPeriod > 0
    & IsolationDelay = 2 * ControlPeriod
    & StartupDelay = 3 * ControlPeriod
    & IsolationDelay > 0 & IsolationDelay <= StartupDelay
    & StartupDelay <= TransferDeadline & T > 0
    & x1 + startupInflow * StartupDelay <= H1
    & x1 + (startupInflow - qprimary) * IsolationDelay >= L1
    & x2 - startupWithdrawal * StartupDelay >= L2
    & x2 + (qprimary - startupWithdrawal) * IsolationDelay <= H2
    & isolationCost >= 0 & backupCost >= 0
    & interventionBudget >= isolationCost + backupCost

postcondition
    L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
    & isolationCommanded = 1 & isolated = 1
    & p2Command = 1 & p2 = 1
    & q1 = 0
    & q2 = qbackup & q2 = p2 * qbackup
    & qin = qbackup & demand = qbackup & qout = demand
    & qdelivered = qout & qdelivered >= qmin
    & isolationClock = IsolationDelay
    & startupClock = StartupDelay
    & transferClock = StartupDelay & transferClock <= TransferDeadline
    & operationClock = T
    & interventionBudget >= 0

game
    {
        {
            { p1 := 0; q1 := 0; }
            ++
            { p1 := 1; q1 := qprimary; }
        }^@;
        isolationCommanded := 1;
        isolated := 0;
        p2Command := 1;
        p2 := 0;
        qin := startupInflow;
        demand := startupWithdrawal;
        qout := demand;
        q2 := p2 * qbackup;
        qdelivered := qout;
        ? qdelivered >= qmin;
        isolationClock := 0;
        startupClock := 0;
        transferClock := 0;
        isolation_phase_one: {
            x1' = qin - q1 - q2,
            x2' = q1 + q2 - qout,
            isolationClock' = 1,
            startupClock' = 1,
            transferClock' = 1
            & isolationClock <= ControlPeriod
            & startupClock <= StartupDelay & transferClock <= TransferDeadline
        };
        ? isolationClock >= ControlPeriod;
        {
            { p1 := 0; q1 := 0; }
            ++
            { p1 := 1; q1 := qprimary; }
        }^@;
        isolation_phase_two: {
            x1' = qin - q1 - q2,
            x2' = q1 + q2 - qout,
            isolationClock' = 1,
            startupClock' = 1,
            transferClock' = 1
            & isolationClock <= IsolationDelay
            & startupClock <= StartupDelay & transferClock <= TransferDeadline
        };
        ? isolationClock >= IsolationDelay;
        isolated := 1;
        q1 := 0;
        {
            { p1 := 0; }
            ++
            { p1 := 1; }
        }^@;
        backup_pending_phase: {
            x1' = qin - q1 - q2,
            x2' = q1 + q2 - qout,
            startupClock' = 1,
            transferClock' = 1
            & startupClock <= StartupDelay & transferClock <= TransferDeadline
        };
        ? startupClock >= StartupDelay;
        ? transferClock <= TransferDeadline;
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
        operation_phase: {
            x1' = qin - q1 - q2,
            x2' = q1 + q2 - qout,
            operationClock' = 1
            & operationClock <= T
        };
        ? operationClock >= T;
    }
'''
    return DelayedIsolationFormalModel(
        model_id=DELAYED_ISOLATION_MODEL_ID,
        envelope_text=text,
        certified_conditions=(
            "L1 <= x1 <= H1 and L2 <= x2 <= H2 with L1,L2 >= 0",
            "P1 is Demon-controlled at the start and after one ControlPeriod while isolation is pending",
            "ControlPeriod > 0, IsolationDelay = 2*ControlPeriod, and StartupDelay = 3*ControlPeriod",
            "qprimary >= startupInflow and qprimary >= startupWithdrawal",
            "x1 + startupInflow*StartupDelay <= H1 and x1 + (startupInflow - qprimary)*IsolationDelay >= L1",
            "x2 - startupWithdrawal*StartupDelay >= L2 and x2 + (qprimary - startupWithdrawal)*IsolationDelay <= H2",
            "startupWithdrawal >= qmin > 0, qbackup >= qmin, and StartupDelay <= TransferDeadline",
            "trusted physical isolation becomes effective exactly after IsolationDelay; P2 startup begins at time zero",
            "post-takeover qin = demand = qout = qbackup and budget covers isolation plus backup activation",
        ),
    )
