"""
Local runner for the attack envelope draft.

Run from the repository root with:
    python mitigation_synthesis/water_attack.py

By default this verifies the canonical Phase 1 `attack.envelope`.
Pass a different envelope path to do a parse smoke test for that file.
"""

import argparse
from pathlib import Path

from cleo.envelope_format import parse_envelope
from cleo.session import EnvelopeSession


DEFAULT_ENVELOPE_PATH = Path(__file__).resolve().with_name("attack.envelope")


IACTIVE = r"""
L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
& x2 = 0
& attackTimer >= 0 & attackTimer <= AttackTime
& AttackTime < attackTimer + Tmin
& AttackTime >= 0
& ometric >= 0 & rmetric >= op1
& L1 <= H1 & L2 <= H2
& f1 >= 0 & f2 >= 0
& T > 0 & Tmin > 0 & Tmin <= T
& c1 >= 0 & c2 >= 0
& op1 >= 0 & ov1 >= 0 & op2 >= 0 & ov2 >= 0
& P1 = 0 & V1 = 1 & P2 = 0 & V2 = 0
"""

IOVER = r"""
L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
& x2 = 0
& attackTimer > AttackTime
& AttackTime >= 0
& ometric >= 0 & rmetric >= 0
& L1 <= H1 & L2 <= H2
& f1 >= 0 & f2 >= 0
& T > 0 & Tmin > 0 & Tmin <= T
& c1 >= 0 & c2 >= 0
& op1 >= 0 & ov1 >= 0 & op2 >= 0 & ov2 >= 0
& P1 = 0 & V1 = 1 & P2 = 0 & V2 = 0
"""

MAIN_LOOP_INV = f"({IACTIVE}) | ({IOVER})"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "envelope",
        nargs="?",
        default=str(DEFAULT_ENVELOPE_PATH),
        help="Envelope to parse or verify.",
    )
    parser.add_argument(
        "--parse-only",
        action="store_true",
        help="Only parse the envelope without running the canonical Phase 1 proof.",
    )
    return parser.parse_args()


def load_spec(envelope_path: Path):
    return parse_envelope(envelope_path.read_text())


def make_session(spec) -> EnvelopeSession:
    session = EnvelopeSession(
        spec.game_str,
        spec.postcondition_str,
        defs_str=spec.defs_str,
    )
    session.set_precondition(spec.precondition_str)
    return session


def verify_phase1(spec) -> int:
    session = make_session(spec)
    needed = session.get_needed_annotations()

    loop_id = next(entry["game_id"] for entry in needed if entry["kind"] == "loop")
    ode_id = next(entry["game_id"] for entry in needed if entry["kind"] == "ode")

    session.set_invariant(loop_id, MAIN_LOOP_INV)
    session.set_invariant(ode_id, MAIN_LOOP_INV)
    session.set_tactic(ode_id, "master")

    result = session.verify()
    for record in result.results:
        status = "PASS" if record.passed else "FAIL"
        message = "" if record.passed else f" {record.feedback[:160]}"
        print(f"{status} {record.obligation.kind} [{record.obligation.game_id}]{message}")

    return 0 if result.all_passed else 1


if __name__ == "__main__":
    args = parse_args()
    envelope_path = Path(args.envelope).resolve()
    spec = load_spec(envelope_path)

    from cleo.parser import (
        parse_defs_from_string,
        parse_formula_from_string,
        parse_game_from_string,
    )

    if spec.defs_str:
        parse_defs_from_string(spec.defs_str)
    parse_formula_from_string(spec.precondition_str)
    parse_formula_from_string(spec.postcondition_str)
    parse_game_from_string(spec.game_str)

    print(f"{envelope_path} parses correctly")

    if args.parse_only:
        raise SystemExit(0)

    if envelope_path != DEFAULT_ENVELOPE_PATH:
        print(
            "No canonical proof profile is configured for this envelope; "
            "use the default attack.envelope for Phase 1 verification."
        )
        raise SystemExit(0)

    raise SystemExit(verify_phase1(spec))
