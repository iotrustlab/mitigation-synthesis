"""CLEO annotation for the separate immediate-isolation safe-hold theorem."""

from __future__ import annotations


from .controlled_safe_hold_formal import CONTROLLED_SAFE_HOLD_PROOF_PROFILE_ID


CONTROLLED_SAFE_HOLD_INVARIANT = r"""
L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2 & L1 >= 0 & L2 >= 0
& isolated = 1 & p2 = 0
& qin = 0 & qout = 0 & qdelivered = 0
& externalDemand > 0 & qmin >= 0
& (p1 = 0 | p1 = 1) & qprimary >= 0
& HoldDuration > 0 & holdClock = 0
& interventionBudget >= 0 & isolationCost >= 0 & holdControlCost >= 0
""".strip()


def attach_controlled_safe_hold_profile(session) -> list[dict[str, str]]:
    """Attach the single invariant required by the mandatory hold ODE."""

    needed = session.get_needed_annotations()
    if len(needed) != 1 or needed[0]["kind"] != "ode" or "holdClock" not in needed[0]["game_str"]:
        raise RuntimeError("controlled safe hold must expose exactly one mandatory hold ODE")
    entry = needed[0]
    session.set_invariant(entry["game_id"], CONTROLLED_SAFE_HOLD_INVARIANT)
    session.set_tactic(entry["game_id"], "implyR(1); solve(1); QE")
    return [
        {
            "game_id": entry["game_id"],
            "kind": "ode",
            "profile": CONTROLLED_SAFE_HOLD_PROOF_PROFILE_ID,
            "tactic": "implyR(1); solve(1); QE",
        }
    ]
