"""Symbolic finite-horizon theorem for independent controlled safe hold.

The hold template is intentionally separate from the P2 takeover theorems. It
models a compromised P1 command before an immediate trusted physical isolator
becomes effective, then closes trusted inflow and demand controls for a
mandatory finite duration. P2 is not used or assumed available.
"""

from __future__ import annotations

from dataclasses import dataclass


CONTROLLED_SAFE_HOLD_MODEL_ID = "controlled-safe-hold-immediate-isolation-v1"
CONTROLLED_SAFE_HOLD_POLICY_ID = "trusted-controlled-safe-hold-v1"
CONTROLLED_SAFE_HOLD_PLANT_MODEL_ID = "controlled-safe-hold-two-tank-v1"
CONTROLLED_SAFE_HOLD_PROOF_PROFILE_ID = "controlled-safe-hold-immediate-isolation-profile-v1"


@dataclass(frozen=True)
class ControlledSafeHoldFormalModel:
    model_id: str
    envelope_text: str
    certified_conditions: tuple[str, ...]


def render_controlled_safe_hold_envelope() -> ControlledSafeHoldFormalModel:
    """Render the policy-specific symbolic game without a runtime binding."""

    text = '''envelope "Controlled safe hold with immediate trusted isolation"

Guideline
    This offline theorem covers the fixed controlled-safe-hold policy, not backup takeover.
    Demon selects the compromised P1 command before trusted isolation becomes effective.
    Immediate isolation, trusted upstream closure, and trusted delivery curtailment then hold both tanks.
    externalDemand remains positive during the hold; qdelivered is actual service and qmin is the incident minimum.
    The theorem proves safety for HoldDuration and deliberately does not prove positive service.

Definitions
    Definitions
        Bool safe(Real x1, Real x2) <-> (L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2);
    End.

    ProgramVariables
        Real x1; Real x2;
        Real L1; Real H1; Real L2; Real H2;
        Real p1; Real p2; Real isolated;
        Real qin; Real qout; Real qdelivered; Real qprimary;
        Real externalDemand; Real qmin;
        Real holdClock; Real HoldDuration;
        Real interventionBudget; Real isolationCost; Real holdControlCost;
    End.

precondition
    L1 < H1 & L2 < H2
    & L1 >= 0 & L2 >= 0
    & L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
    & qprimary >= 0
    & externalDemand > 0 & qmin >= 0
    & HoldDuration > 0
    & isolationCost >= 0 & holdControlCost >= 0
    & interventionBudget >= isolationCost + holdControlCost

postcondition
    L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
    & isolated = 1 & p2 = 0
    & qin = 0 & qout = 0 & qdelivered = 0
    & externalDemand > 0 & qmin >= 0
    & holdClock = HoldDuration
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
        qout := 0;
        qdelivered := 0;
        interventionBudget := interventionBudget - isolationCost;
        interventionBudget := interventionBudget - holdControlCost;
        holdClock := 0;
        hold_ode: {
            x1' = qin - (1-isolated) * p1 * qprimary,
            x2' = (1-isolated) * p1 * qprimary - qout,
            holdClock' = 1
            & holdClock <= HoldDuration
        };
        ? holdClock >= HoldDuration;
    }
'''
    return ControlledSafeHoldFormalModel(
        model_id=CONTROLLED_SAFE_HOLD_MODEL_ID,
        envelope_text=text,
        certified_conditions=(
            "closed initial tank bounds L1 <= x1 <= H1 and L2 <= x2 <= H2 with nonnegative lower bounds",
            "Demon selects p1 in {0,1} before immediate trusted physical isolation",
            "trusted isolation, upstream closure qin=0, and demand/delivery closure qout=qdelivered=0",
            "externalDemand > 0 remains explicit while actual delivery is zero and qmin is represented separately",
            "HoldDuration > 0 forces one finite physical ODE evolution; the ODE domain does not assume tank safety",
            "interventionBudget covers isolationCost plus holdControlCost",
        ),
    )
