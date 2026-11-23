"""Verify a small source-bounded Attleboro procedure choice with CLEO.

The proposed Angel choice is the synthesis object: it admits Remote or local
Hand only under its documented authority guard. Verification is deliberately
limited to command eligibility, not physical service or optimality.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from cleo.envelope_format import parse_envelope
from cleo.parser import parse_defs_from_string, parse_formula_from_string, parse_game_from_string
from cleo.session import EnvelopeSession

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "attleboro_documented_choice.envelope"


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
    annotations = session.get_needed_annotations()
    if annotations:
        raise RuntimeError(f"unexpected loop/ODE annotations: {annotations}")
    result = session.verify()
    obligations = [
        {"kind": r.obligation.kind, "game_id": r.obligation.game_id,
         "passed": r.passed, "feedback": "" if r.passed else r.feedback}
        for r in result.results
    ]
    receipt = {
        "experiment": "Attleboro documented command-location choice",
        "source_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "status": "VERIFIED" if result.all_passed else "UNVERIFIED",
        "claim": "eligible command location only; no physical plant or service theorem",
        "ownership": "Angel chooses a documented eligible branch; environment state is fixed by the precondition",
        "branch_guards": [
            "utility, utility MTS, no generator run, Remote selector, cleared reset, no trip",
            "generator MTS, generator ready, Hand selector, local actor, no trip",
        ],
        "obligations": obligations,
    }
    if args.output is not None:
        args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if result.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
