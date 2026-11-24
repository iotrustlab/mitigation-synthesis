"""Finite, single-assignment stage relations with exact execution and dL output."""

from __future__ import annotations

import ast
import operator
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache


@lru_cache(maxsize=512)
def _tree(expr):
    return ast.parse(expr, mode="eval").body


_OPERATORS = {
    ast.Add: ("+", operator.add), ast.Sub: ("-", operator.sub),
    ast.Mult: ("*", operator.mul), ast.Div: ("/", operator.truediv),
    ast.Eq: ("=", operator.eq), ast.Lt: ("<", operator.lt),
    ast.LtE: ("<=", operator.le), ast.GtE: (">=", operator.ge),
    ast.Gt: (">", operator.gt), ast.NotEq: ("!=", operator.ne),
}


def _interpret(node, state):
    """A None state requests dL rendering of the same expression tree."""
    render = state is None
    if isinstance(node, ast.Name):
        return node.id if render else state[node.id]
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return str(node.value) if render else Fraction(node.value)
    if isinstance(node, ast.BoolOp):
        values = [_interpret(item, state) for item in node.values]
        conjunction = isinstance(node.op, ast.And)
        if render:
            return "(" + (" & " if conjunction else " | ").join(values) + ")"
        return all(values) if conjunction else any(values)
    if isinstance(node, ast.BinOp):
        lhs, op, rhs = node.left, node.op, node.right
    elif isinstance(node, ast.Compare) and len(node.ops) == 1:
        lhs, op, rhs = node.left, node.ops[0], node.comparators[0]
    else:
        raise ValueError("expression outside the finite procedure IR")
    symbol, fn = _OPERATORS[type(op)]
    a, b = _interpret(lhs, state), _interpret(rhs, state)
    return f"({a}{symbol}{b})" if render else fn(a, b)


def expr(source, state=None):
    return _interpret(_tree(source), state)


@dataclass(frozen=True)
class Assignment:
    """Finite guarded alternatives; each value expression uses earlier variables."""
    name: str
    # Each branch is a guard (None means true) and a value expression.
    alternatives: tuple[tuple[str | None, str], ...]

    @classmethod
    def nominal(cls, name, value):
        return cls(name, ((None, value),))

    @classmethod
    def indicator(cls, name, predicate):
        return cls.conditional(name, predicate, "1", "0")

    @classmethod
    def conditional(cls, name, predicate, yes, no):
        return cls(name, ((predicate, yes), ("!" + predicate, no)))

    def relation(self):
        branches = []
        for guard, value in self.alternatives:
            equality = f"{self.name}={expr(value)}"
            if guard is None:
                branches.append(equality)
            else:
                prefix = "!" if guard.startswith("!") else ""
                branches.append(f"({prefix}{expr(guard.lstrip('!'))} & {equality})")
        return "(" + " | ".join(branches) + ")" if branches else "(0=1)"

    def values(self, state):
        values = set()
        for guard, value in self.alternatives:
            if guard is None or bool(expr(guard.lstrip("!"), state)) != guard.startswith("!"):
                values.add(expr(value, state))
        return sorted(values)


@dataclass(frozen=True)
class Stage:
    name: str
    assignments: tuple[Assignment, ...]


def executions(stages, initial):
    """All terminal states; unavailable branches have an empty value set."""
    states = [dict(initial)]
    for stage in stages:
        for assignment in stage.assignments:
            states = [dict(state, **{assignment.name: value}) for state in states
                      for value in assignment.values(state)]
    return states


def hybrid_program(assignments):
    """SSA lowering: sample fresh slots, then constrain their joint transition.

    Each RHS mentions only earlier slots. Moving the tests after the samples
    preserves exactly the feasible paths, including disabled and unknown paths.
    """
    samples = " ".join(f"{a.name}:=*;" for a in assignments)
    relation = "\n      & ".join(a.relation() for a in assignments)
    return f"{samples}\n    ? ({relation});"
