"""The procedure IR drives both trace witnesses and the archived dL obligations."""

from dataclasses import replace
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from recovery_experiment.procedure_formalism.attleboro import attleboro
from recovery_experiment.procedure_formalism.dependency_semantics import transition
from recovery_experiment.procedure_formalism.formal_ir import Assignment, Stage, executions
from recovery_experiment.procedure_formalism.formal_model import build_model, retained_start
from recovery_experiment.procedure_formalism.procedure import DependencyStatus as Status
from recovery_experiment.procedure_formalism.verify import ROOT, _matches, verified, verified_violation


class ProcedureFormalTests(unittest.TestCase):
    def test_dependency_alphabets_and_disabled_branch(self):
        node = attleboro()["remote"].required_dependencies["observer"]
        nominal = Assignment.nominal("observed", "q")
        expected = {
            Status.TRUSTED: [4], Status.COMPROMISED: [0, 10],
            Status.UNAVAILABLE: [], Status.UNKNOWN: [0, 4, 10],
        }
        for status, values in expected.items():
            with self.subTest(status=status):
                relation = transition(replace(node, status=status), nominal, ("0", "10"))
                self.assertEqual(relation.values({"q": 4}), values)
                if status is Status.UNAVAILABLE:
                    self.assertEqual(relation.relation(), "(0=1)")

    def test_mandatory_duration_and_recurrence(self):
        model = build_model(attleboro()["remote"])
        (state,) = model.executions()
        self.assertEqual([state[f"tick{i}"] for i in (1, 2, 3)], [1, 2, 3])
        self.assertEqual([state[f"run{i}"] for i in (1, 2, 3)], [0, 1, 1])
        self.assertEqual([state[f"flow{i}"] for i in (1, 2, 3)], [0, 4, Fraction(32, 5)])
        self.assertEqual(state["observedPressure"], Fraction(246, 5))
        self.assertEqual(state["physical"], state["established"])
        self.assertEqual(state["safe"], 1)

    def test_post_clamp_and_unsafe_initial_state(self):
        model = build_model(attleboro(initial_state={"initial_flow": 0.01})["remote"])
        self.assertEqual(model.executions()[0]["flow1"], 0)
        unsafe = build_model(attleboro(initial_state={"ph_out_of_range": 1})["remote"])
        self.assertEqual(unsafe.executions()[0]["safe"], 0)

    def test_momentary_start_and_feedback_lag(self):
        states = executions((Stage("controller", tuple(retained_start())),), {})
        self.assertEqual(len(states), 4)
        for s in states:
            self.assertEqual([s[f"out{i}"] for i in (1, 2, 3)], [s["eligible"]] * 3)
            if s["eligible"]:
                self.assertEqual(s["seal3"], s["secondFeedback"])
                self.assertEqual(s["wait3"], 0 if s["secondFeedback"] else 3)

    def test_unavailable_and_compromised_delivery_affect_execution(self):
        disabled = build_model(attleboro({"delivery": Status.UNAVAILABLE})["remote"])
        self.assertEqual(disabled.executions(), [])
        compromised = build_model(attleboro({"delivery": Status.COMPROMISED})["remote"])
        self.assertEqual({(s["output"], s["delivered"], s["physical"]) for s in compromised.executions()},
                         {(1, 0, 0), (1, 1, 1)})
        self.assertNotEqual(disabled.sha256, compromised.sha256)

    def test_unknown_observer_preserves_correlation(self):
        model = build_model(attleboro({"observer": Status.UNKNOWN})["remote"])
        states = model.executions()
        self.assertEqual(len(states), 5)
        for s in states:
            if s["trusted"]:
                self.assertEqual(s["observed"], s["q"])
                self.assertEqual(s["observedPressure"], s["pressure"])
                self.assertEqual(s["established"], 1)
            else:
                self.assertIn(s["observed"], (0, 10))
                self.assertIn(s["observedPressure"], (30, 90))
                self.assertEqual(s["established"], 0)

    def test_unsupported_plant_is_unresolved(self):
        with self.assertRaisesRegex(ValueError, "unsupported water plant model"):
            build_model(replace(attleboro()["remote"], plant_model="unbound-plant"))

    def test_archived_formulas_match_all_nine_model_instances(self):
        from recovery_experiment.procedure_formalism.evaluation import MUTATIONS

        for i in (0, 1, 2, 4, 5, 7, 8, 9, 13):
            with self.subTest(mutation=i):
                case = MUTATIONS[i]
                model = build_model(attleboro(case.dependencies, case.states)["remote"])
                archived = (ROOT / "models" / f"M{i}.kyx").read_text()
                self.assertEqual(archived, model.archive(violation=bool(i)))
                self.assertEqual(hashlib.sha256(model.archive().encode()).hexdigest(), model.sha256)
                self.assertTrue(verified_violation(model) if i else verified(model))
                self.assertFalse(verified(model) if i else verified_violation(model))

    def test_incomplete_or_stale_proof_record_fails_closed(self):
        model = build_model(attleboro()["remote"])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(ROOT / "models", root / "models")
            shutil.copytree(ROOT / "proof_records", root / "proof_records")
            self.assertTrue(_matches(model, False, root))
            record = root / "proof_records" / "verification.json"
            index = json.loads(record.read_text())
            row = index["models"][model.sha256]
            proof = root / "proof_records" / "M0" / "end_to_end.kyp"
            # A manifest hash alone cannot substitute another theorem's artifact.
            wrong = proof.with_name("execution_witness.kyp").read_bytes()
            proof.write_bytes(wrong)
            row["obligations"]["end_to_end"]["proof_sha256"] = hashlib.sha256(wrong).hexdigest()
            record.write_text(json.dumps(index))
            self.assertFalse(_matches(model, False, root))
            del row["obligations"]["execution_witness"]
            record.write_text(json.dumps(index))
            self.assertFalse(_matches(model, False, root))
