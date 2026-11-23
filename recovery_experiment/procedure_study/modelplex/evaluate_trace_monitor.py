"""Evaluate the generated bad-power ModelPlex formula on one saved trace.

This checks only visible controller outputs under the formula's bad-power
branch. ``startDemand`` is unobserved and must pass for both Boolean values;
``prevResetReqpost`` is unobserved and is existentially projected.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import re
from pathlib import Path


HERE = Path(__file__).resolve().parent
DEFAULT_MONITOR = HERE / "attleboro_bad_power_ctrl.kym"

VISIBLE_FIELDS = {
    "utility": "ATT_Utility_Available",
    "mtsGen": "ATT_MTS_Generator",
    "genRun": "ATT_Generator_Running",
    "selectorRemote": "ATT_Selector_Remote",
    "trip": "ATT_Trip",
    "resetReq": "ATT_Reset_Request",
    "resetPendingpost": "ATT_Reset_Pending",
    "remoteEligiblepost": "ATT_Remote_Eligible",
    "remoteStartpost": "ATT_Remote_Start",
}
UNOBSERVED = {"startDemand", "prevResetReqpost"}
EXPECTED_NAMES = set(VISIBLE_FIELDS) | UNOBSERVED
TOKEN = re.compile(r"[A-Za-z_][A-Za-z_0-9]*|\d+|!=|=|[()&|!]", re.ASCII)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_monitor(path: Path) -> ast.Expression:
    source = re.sub(r"/\*.*?\*/", "", path.read_text(), flags=re.DOTALL).strip()
    pieces: list[str] = []
    cursor = 0
    for match in TOKEN.finditer(source):
        if source[cursor : match.start()].strip():
            raise ValueError(f"unsupported monitor syntax at {cursor}")
        token = match.group()
        pieces.append({"=": "==", "&": " and ", "|": " or ", "!": " not "}.get(token, token))
        cursor = match.end()
    if source[cursor:].strip():
        raise ValueError(f"unsupported monitor syntax at {cursor}")
    expression = ast.parse("".join(pieces), mode="eval")
    names = {node.id for node in ast.walk(expression) if isinstance(node, ast.Name)}
    if names != EXPECTED_NAMES:
        raise ValueError(f"monitor symbol set changed: {sorted(names)}")
    return expression


def evaluate(node: ast.AST, values: dict[str, int]) -> bool | int:
    if isinstance(node, ast.Expression):
        return evaluate(node.body, values)
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        return all(bool(evaluate(item, values)) for item in node.values)
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        return any(bool(evaluate(item, values)) for item in node.values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not bool(evaluate(node.operand, values))
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
        left = evaluate(node.left, values)
        right = evaluate(node.comparators[0], values)
        if isinstance(node.ops[0], ast.Eq):
            return left == right
        if isinstance(node.ops[0], ast.NotEq):
            return left != right
    if isinstance(node, ast.Name) and node.id in EXPECTED_NAMES:
        return values[node.id]
    if isinstance(node, ast.Constant) and type(node.value) is int and node.value in (0, 1):
        return node.value
    raise ValueError(f"unsupported monitor AST node: {ast.dump(node)}")


def projected_match(formula: ast.Expression, row: dict[str, str]) -> tuple[bool, dict[str, int]]:
    values = {symbol: int(row[column]) for symbol, column in VISIBLE_FIELDS.items()}
    if not all(value in (0, 1) for value in values.values()):
        raise ValueError("monitor input must be Boolean-coded as 0 or 1")
    hidden_witnesses: dict[str, int] = {}
    for demand in (0, 1):
        matches = [
            hidden
            for hidden in (0, 1)
            if evaluate(formula, values | {"startDemand": demand, "prevResetReqpost": hidden})
        ]
        if not matches:
            return False, hidden_witnesses
        hidden_witnesses[str(demand)] = matches[0]
    return True, hidden_witnesses


def applicable(row: dict[str, str]) -> bool:
    return any(int(row[column]) == 1 for column in ("ATT_MTS_Generator", "ATT_Generator_Running")) or int(
        row["ATT_Utility_Available"]
    ) == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--monitor", type=Path, default=DEFAULT_MONITOR)
    parser.add_argument("--trace", type=Path, required=True, help="Attleboro tags.csv from sphere-usecases")
    parser.add_argument("--output", type=Path, help="optional JSON receipt path")
    args = parser.parse_args()

    formula = parse_monitor(args.monitor)
    with args.trace.open(newline="") as stream:
        trace = list(csv.DictReader(stream))
    if not trace:
        raise ValueError("empty trace")
    missing = set(VISIBLE_FIELDS.values()) - set(trace[0])
    if missing:
        raise ValueError(f"missing trace columns: {sorted(missing)}")

    checked = []
    failures = []
    for tick, row in enumerate(trace):
        if not applicable(row):
            continue
        passed, witnesses = projected_match(formula, row)
        checked.append({"tick": tick, "passed": passed, "hidden_witness_by_demand": witnesses})
        if not passed:
            failures.append(tick)
    if not checked:
        raise ValueError("trace has no bad-power rows in monitor scope")

    mutation_tick = next((item["tick"] for item in checked if trace[item["tick"]]["ATT_MTS_Generator"] == "1"), checked[0]["tick"])
    mutations = []
    for column in ("ATT_Remote_Eligible", "ATT_Remote_Start", "ATT_Reset_Pending"):
        changed = dict(trace[mutation_tick])
        changed[column] = str(1 - int(changed[column]))
        passed, witnesses = projected_match(formula, changed)
        mutations.append({"tick": mutation_tick, "flipped_column": column, "accepted_by_monitor": passed, "hidden_witness_by_demand": witnesses})

    status = "PASS" if not failures and all(not item["accepted_by_monitor"] for item in mutations) else "FAIL"
    delivery_mismatches = [
        tick
        for tick, row in enumerate(trace)
        if "ATT_Delivered_Remote_Start" in row
        and row["ATT_Delivered_Remote_Start"] != row["ATT_Remote_Start"]
    ]
    result = {
        "status": status,
        "monitor_sha256": sha256(args.monitor),
        "trace_sha256": sha256(args.trace),
        "rows_total": len(trace),
        "applicable_bad_power_rows": len(checked),
        "first_applicable_tick": checked[0]["tick"],
        "last_applicable_tick": checked[-1]["tick"],
        "failing_ticks": failures,
        "demand_values_checked": [0, 1],
        "unobserved_post_symbol": "prevResetReqpost, existentially projected over {0,1}",
        "visible_field_mapping": VISIBLE_FIELDS,
        "mutations": mutations,
        "downstream_delivery_mismatch_rows": len(delivery_mismatches),
        "downstream_delivery_is_not_a_monitor_input": True,
        "scope": "saved synthetic same-scan input/output rows; bad-power controller branch only; no physical plant or network monitor",
    }
    if args.output is not None:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
