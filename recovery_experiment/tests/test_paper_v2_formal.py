"""Regression tests for partial executions and v2 proof-to-claim bindings."""

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from recovery_experiment.procedure_formalism.formal_ir import Assignment, Stage
from recovery_experiment.procedure_formalism.milestone2 import cost
from recovery_experiment.procedure_formalism.paper_v2.formal import audit_prefixes, nominal_cases
from recovery_experiment.procedure_formalism.paper_v2.formal_reports import generate


class FormalEvidenceTests(unittest.TestCase):
    def test_one_successful_diamond_can_hide_an_adverse_blocked_prefix(self):
        branch = Assignment("bit", ((None, "0"), (None, "1")))
        filter_zero = Assignment("output", (("bit==1", "1"),))
        original = nominal_cases()[0]
        incomplete = replace(original, initial={}, stages=(Stage("delivery", (branch, filter_zero)),))
        with self.assertRaisesRegex(ValueError, "silently blocks"):
            audit_prefixes(incomplete)

    def test_symbolic_coefficients_cannot_silently_choose_a_successor(self):
        original = nominal_cases()[-1]
        stage = Stage("choice", (Assignment.conditional("bit", "wTime==0", "0", "1"),))
        with self.assertRaisesRegex(ValueError, "weights affect branching"):
            audit_prefixes(replace(original, stages=(stage,)))
        later_guard = Stage("later", (Assignment.conditional("bit", "J==0", "0", "1"),))
        with self.assertRaisesRegex(ValueError, "weights affect branching"):
            audit_prefixes(replace(original, stages=(*original.stages, later_guard)))

    def test_final_meter_alone_cannot_certify_earlier_service(self):
        _, late_manual = cost.plans(cost.SCENARIOS["C6"])
        for state in late_manual.terminal():
            self.assertEqual(state["credible"], 1)
            self.assertEqual(state["reading"], state["q"])
            self.assertGreaterEqual(state["q"], state["minimum"])
            self.assertGreater(state["start"], state["deadline"])
            self.assertEqual(state["physical"], 0)

    def test_matrix_and_cases_use_checked_formulas(self):
        with TemporaryDirectory() as target:
            output = Path(target)
            generate(output)
            matrix = json.loads((output / "proof_obligation_matrix.json").read_text())
            rows = matrix["fixed_procedure_rows"]
            self.assertEqual(len(rows), 40)
            self.assertEqual(matrix["new_dL_theorems"], 20)
            for row in rows:
                if row["status"] == "NOT_APPLICABLE":
                    self.assertEqual(row["obligation"], "O8")
                    self.assertNotIn(row["case"], ("P2", "P3"))
                else:
                    self.assertEqual(row["status"], "PROVED")
                    self.assertTrue(row["proof_sha256"])
            cases = json.loads((output / "canonical_semantic_cases.json").read_text())
            variants = {k:v for case in cases for k,v in case["variants"].items()}
            self.assertEqual(variants["M5"]["classification"], "REJECTED")
            self.assertEqual(variants["M13"]["classification"], "UNKNOWN")
            self.assertEqual(variants["M5"]["witness"], variants["M13"]["witness"])
            self.assertEqual(variants["CHP0"]["device"], "ESTABLISHED")
            self.assertEqual(variants["CHP0"]["customer_service"], "UNKNOWN")
            self.assertEqual(variants["CHP0"]["proofs"], [])
