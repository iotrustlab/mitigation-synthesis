"""Regressions for distinct baseline decisions and the cost indifference surface."""
import json
import tempfile
import unittest
from collections import Counter
from fractions import Fraction
from pathlib import Path

from recovery_experiment.procedure_formalism.paper_v2.comparison import baselines, costs, dot


class ReviewerComparisonTests(unittest.TestCase):
    def test_denominators_and_unknown_static_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            baselines(Path(tmp))
            data = json.loads((Path(tmp) / "baseline_contingency.json").read_text())
        for row in data["totals"]:
            cells = [n for k, n in row.items() if k.startswith(("retained_", "not_retained_", "inapplicable_"))]
            self.assertEqual(sum(cells), 68)
        unresolved = [r for r in data["rows"] if r["B2"] == "UNRESOLVED"]
        self.assertEqual({r["scenario"] for r in unresolved}, {"M13", "MER10"})
        self.assertTrue(all(r["B4"] == "UNKNOWN" for r in unresolved))
        self.assertEqual(data["union_retained_by_reference"], {"PROVED": 11, "REJECTED": 47, "UNKNOWN": 6})
        self.assertEqual(Counter(r["B4"] for r in data["rows"] if r["B3"] == "INAPPLICABLE"),
                         {"PROVED": 4, "REJECTED": 23})

    def test_policy_distance_and_simultaneous_ties(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            costs(dest)
            delta = json.loads((dest / "cost_break_even.json").read_text())["P3_minus_P2_coefficients"]
            policies = json.loads((dest / "cost_sensitivity.json").read_text())["policies"]
        for name, nearest in (("COST-W1", "-3/4"), ("COST-W2", "-33/40"), ("COST-W3", "-1/2")):
            policy = policies[name]
            self.assertEqual(policy["closest_tie_with_crossing"]["relative_change"], nearest)
            self.assertEqual({r["selection"] for r in policy["perturbations"]}, {policy["selection"]})
            self.assertEqual(len(policy["perturbations"]), 16)
            radius = Fraction(policy["simultaneous_relative_infinity_norm_to_tie"])
            starting = policy["signed_P3_minus_P2"]
            tie = [w * (1 - radius if starting * d > 0 else 1 + radius)
                   for w, d in zip(policy["weights"], delta)]
            self.assertEqual(dot(tie, delta), 0)
