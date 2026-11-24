"""End-to-end regression checks for the bounded historical fixture."""

import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from recovery_experiment.procedure_formalism.attleboro import attleboro
from recovery_experiment.procedure_formalism.classifier import Reason, classify
from recovery_experiment.procedure_formalism.evaluation import ROOT, baselines, evaluate, write_results
from recovery_experiment.procedure_formalism.procedure import DependencyStatus as DS, EvidenceStatus, ProcedureStatus


class ProcedureDecisionTests(unittest.TestCase):
    def test_failed_proof_is_unknown(self):
        with patch("recovery_experiment.procedure_formalism.classifier.verified", return_value=False):
            decision = classify(attleboro()["remote"])
        self.assertEqual(decision.result, ProcedureStatus.UNKNOWN)
        self.assertIn(Reason.FORMAL_PROOF_UNRESOLVED, decision.reasons)

    def test_missing_theorem_inputs(self):
        proc = attleboro()["remote"]
        self.assertEqual(classify(replace(proc, plant_model=None)).reasons, (Reason.PLANT_MODEL_MISSING,))
        evidence = dict(proc.evidence_status_by_field, freshness_requirement=EvidenceStatus.UNKNOWN)
        decision = classify(replace(proc, evidence_status_by_field=evidence))
        self.assertEqual(decision.result, ProcedureStatus.UNKNOWN)
        self.assertIn(Reason.EVIDENCE_INSUFFICIENT, decision.reasons)

    def test_known_unavailable_even_without_complete_model(self):
        proc = attleboro({"vfd": DS.UNAVAILABLE})["remote"]
        for incomplete in (replace(proc, actor_ready_time=None), replace(proc, plant_model=None)):
            decision = classify(incomplete)
            self.assertEqual(decision.result, ProcedureStatus.REJECTED)
            self.assertIn(Reason.ACTUATOR_UNAVAILABLE, decision.reasons)

    def test_starts_in_time_but_completes_late(self):
        proc = replace(attleboro()["remote"], actor_ready_time=1)
        decision = classify(proc)
        self.assertEqual(decision.result, ProcedureStatus.REJECTED)
        self.assertIn(Reason.DEADLINE_MISSED, decision.reasons)
        self.assertEqual(decision.witness["t"], 4)

    def test_common_resources_exclude_both_candidates(self):
        for resource in ("pump", "vfd", "motor_power"):
            procs = attleboro({resource: DS.UNAVAILABLE})
            for name in ("remote", "hand"):
                with self.subTest(resource=resource, candidate=name):
                    decision = classify(procs[name])
                    self.assertEqual(decision.result, ProcedureStatus.REJECTED)
                    self.assertIn(resource, decision.basis)

    def test_baselines_keep_different_boundaries(self):
        procs = attleboro({"delivery": DS.UNAVAILABLE})
        self.assertEqual(baselines(procs["remote"]), {"B1": "ACCEPT", "B2": "DECLINE", "B3": "ACCEPT"})

    def test_entire_matrix(self):
        data = evaluate()
        matrix = data["attleboro_mutation_matrix"]
        self.assertEqual([r["mutation"] for r in matrix], [f"M{i}" for i in range(15)])
        statuses = [row["assessments"][0]["result"] for row in matrix]
        self.assertEqual(statuses, ["PROVED"] + ["REJECTED"] * 12 + ["UNKNOWN", "REJECTED"])
        failure = matrix[5]["assessments"][0]["execution_witness"]
        self.assertEqual((failure["output"], failure["delivered"], failure["physical"]), (1, 0, 0))
        blocked = matrix[7]["assessments"][0]["execution_witness"]
        self.assertEqual((blocked["run"], blocked["q"]), (1, 0))
        for i in (8, 9):
            state = matrix[i]["assessments"][0]["execution_witness"]
            self.assertEqual((state["physical"], state["established"]), (1, 0))
        self.assertEqual(matrix[14]["selection"], "NO_ASSURED_RECOVERY")
        reasons = [row["reason"][0] for row in matrix[14]["assessments"]]
        self.assertEqual(reasons, ["COMMUNICATION_UNAVAILABLE", "ACTOR_UNAVAILABLE", "SERVICE_NOT_ESTABLISHED"])

    def test_result_reproduction(self):
        with tempfile.TemporaryDirectory() as directory:
            write_results(Path(directory))
            for f in Path(directory).glob("*.json"):
                self.assertEqual(f.read_bytes(), (ROOT / "results" / f.name).read_bytes())
                self.assertTrue(json.loads(f.read_text()))

    def test_historical_input_bytes(self):
        for line in (ROOT / "historical_inputs.sha256").read_text().splitlines():
            expected, name = line.split("  ", 1)
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((ROOT.parents[1] / name).read_bytes()).hexdigest(), expected)
