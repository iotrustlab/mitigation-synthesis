"""Run the finite research flow ODE obligation in CLEO."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from cleo.envelope_format import parse_envelope
from cleo.parser import parse_defs_from_string, parse_formula_from_string, parse_game_from_string
from cleo.session import EnvelopeSession

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "attleboro_sampled_flow.envelope"
ODE_PRE = "0 <= q0 & q0 <= 10 & (target = 0 | target = 10) & q = q0 & t = 0"
ODE_TACTIC = "implyR(1); solve(1); QE"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="optional JSON receipt path")
    args = parser.parse_args()
    content = SOURCE.read_text()
    spec = parse_envelope(content)
    if spec.defs_str:
        parse_defs_from_string(spec.defs_str)
    parse_formula_from_string(spec.precondition_str)
    parse_formula_from_string(spec.postcondition_str)
    parse_game_from_string(spec.game_str)
    session = EnvelopeSession(spec.game_str, spec.postcondition_str, defs_str=spec.defs_str)
    session.set_precondition(spec.precondition_str)
    needed = session.get_needed_annotations()
    if len(needed) != 1 or needed[0]["kind"] != "ode":
        raise RuntimeError(f"expected one ODE, got {needed}")
    game_id = needed[0]["game_id"]
    session.set_invariant(game_id, ODE_PRE)
    session.set_tactic(game_id, ODE_TACTIC)
    result = session.verify()
    obligations = [
        {"kind": r.obligation.kind, "game_id": r.obligation.game_id,
         "passed": r.passed, "feedback": "" if r.passed else r.feedback}
        for r in result.results
    ]
    receipt = {
        "experiment": "Attleboro sampled-slope research flow ODE",
        "source_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "status": "VERIFIED" if result.all_passed else "UNVERIFIED",
        "claim": "pre-clamp research flow remains in [0,10] L/s after one 0.1 s phase",
        "scope": "frozen sampled-slope interpolation of the SPHERE simulator; no site hydraulic or service theorem",
        "ode_precondition": ODE_PRE,
        "ode_tactic": ODE_TACTIC,
        "obligations": obligations,
    }
    if args.output is not None:
        args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if result.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
