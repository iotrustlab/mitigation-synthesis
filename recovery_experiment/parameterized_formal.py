"""Offline parameterized theorem for the fixed trusted-backup takeover policy."""

from __future__ import annotations

from dataclasses import dataclass


PARAMETERIZED_MODEL_ID = "parameterized-timed-takeover-v1"
PARAMETERIZED_POLICY_ID = "trusted-backup-takeover-v1"
PARAMETERIZED_PLANT_MODEL_ID = "synthetic-two-tank-v1"


@dataclass(frozen=True)
class ParameterizedFormalModel:
    model_id: str
    envelope_text: str
    certified_conditions: tuple[str, ...]


def render_parameterized_recovery_envelope() -> ParameterizedFormalModel:
    """Render the symbolic theorem; no concrete context is instantiated here."""

    text = '''envelope "Parameterized timed trusted backup takeover recovery"

Guideline
    Offline theorem for all safe initial tank levels and symbolic capacity, timing, and budget values
    satisfying the stated assumptions. It covers one exact startup interval and one mandatory operation interval.

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
    L1 < H1 & L2 < H2
    & L1 >= 0 & L2 >= 0
    & L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
    & qprimary >= 0 & qbackup >= qmin & qmin > 0
    & StartupDelay > 0 & T > 0 & StartupDelay <= RecoveryDeadline
    & isolationCost >= 0 & backupCost >= 0
    & interventionBudget >= isolationCost + backupCost

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
    {
        {
            { p1 := 0; }
            ++
            { p1 := 1; }
        }^@;
        isolated := 1;
        p2 := 0;
        qin := 0;
        qd := 0;
        q1 := 0;
        q2 := p2 * qbackup;
        qdelivered := 0;
        startupClock := 0;
        recoveryClock := 0;
        startup_ode: {
            x1' = qin - q1 - q2,
            x2' = q1 + q2 - qd,
            startupClock' = 1,
            recoveryClock' = 1
            & x1 >= 0 & x2 >= 0
            & startupClock <= StartupDelay & recoveryClock <= RecoveryDeadline
        };
        ? startupClock >= StartupDelay;
        ? recoveryClock <= RecoveryDeadline;
        {
            { p1 := 0; }
            ++
            { p1 := 1; }
        }^@;
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
        operation_ode: {
            x1' = qin - q1 - q2,
            x2' = q1 + q2 - qd,
            recoveryClock' = 0,
            operationClock' = 1
            & x1 >= 0 & x2 >= 0 & operationClock <= T
        };
        ? operationClock >= T;
    }
'''
    return ParameterizedFormalModel(
        model_id=PARAMETERIZED_MODEL_ID,
        envelope_text=text,
        certified_conditions=(
            "L1 < H1, L2 < H2, and nonnegative lower bounds",
            "L1 <= x1 <= H1 and L2 <= x2 <= H2",
            "qprimary >= 0 and qbackup >= qmin > 0",
            "0 < StartupDelay <= RecoveryDeadline and 0 < T",
            "0 <= isolationCost, 0 <= backupCost, and budget covers both actions",
            "immediate effective trusted isolation and balanced qin = qd = qbackup",
        ),
    )
