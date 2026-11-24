import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from recovery_experiment.procedure_formalism.formal_ir import Assignment, Stage
from recovery_experiment.procedure_formalism.paper_v5 import ablation, assessments


class AssessmentAblations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.queries = assessments.queries()
        cls.basis = assessments.evidence_rows(cls.queries)
        cls.data = ablation.results(cls.queries, cls.basis)

    def test_previous_labels_and_proofs_have_independent_bases(self):
        self.assertEqual(len({r["assessment_id"] for r in self.basis}), 68)
        self.assertEqual(Counter(r["evidence_outcome"] for r in self.basis),
                         {"PROVED": 11, "REJECTED": 51, "UNKNOWN": 6})
        for row in self.basis:
            self.assertEqual(row["evidence_outcome"], row["B4"])
            for source in (row["supporting_artifact"], row["supporting_context"]):
                path = Path(source.split("#")[0])
                self.assertFalse(path.is_absolute())
                self.assertTrue((assessments.ROOT / path).is_file(), source)
            if row["classification_basis"] in (assessments.POS, assessments.NEG):
                self.assertTrue(row["supporting_artifact"].endswith(".kyp"))
        device = [r for r in self.basis if r["domain"] == "chp" and assessments.TRACE in r["additional_evidence"]]
        self.assertEqual(Counter(r["evidence_outcome"] for r in device), {"REJECTED": 1, "UNKNOWN": 4})

    def test_partial_guard_and_terminal_counterexamples_defeat_retention(self):
        choice = Assignment("a", ((None, "0"), (None, "1")))
        premature = Assignment("b", (("a==1", "1"),))
        self.assertFalse(ablation.all_paths_meet((Stage("partial", (choice, premature)),), {}, "b==1"))
        self.assertFalse(ablation.all_paths_meet((Stage("adverse", (choice,)),), {}, "a==1"))

    def test_stage_changes_have_named_witnesses_and_explicit_denominators(self):
        by_name = {r["variant"]: r for r in self.data["totals"]}
        self.assertEqual([r["applicable"] for r in self.data["totals"]], [68, 57, 40, 64, 57, 24])
        self.assertEqual([r["retained_without_support"] for r in self.data["totals"]], [0, 6, 4, 5, 7, 0])
        for r in self.data["totals"]:
            self.assertEqual(r["retained_known_failure"] + r["retained_unresolved"] + r["retained_proved"], r["retained"])
            self.assertEqual(sum(x["applicable"] for x in self.data["by_domain"] if x["variant"] == r["variant"]),
                             r["applicable"])
        self.assertEqual({i.split("/")[1] for i in by_name["COLLAPSE_DELIVERY"]["decisive_assessments"]},
                         {"M5", "M13", "MER6", "MER10"})
        self.assertEqual(by_name["COLLAPSE_PLANT"]["retained_unresolved"], 2)
        for name in ("H8", "H9", "MER8"):
            self.assertTrue(any(i.split("/")[1] == name for i in by_name["NO_OBSERVATION"]["decisive_assessments"]))

    def test_cloned_status_and_single_event_placement_answer_different_questions(self):
        feed = next(r for r in self.data["clone_placement_diagnostic"] if r["scenario"] == "C3")
        self.assertEqual(feed["original_retained"], [])
        self.assertEqual(feed["cloned_retained_all_placements"], [])
        self.assertEqual(len(feed["placements"]), 2)
        for placement in feed["placements"]:
            self.assertEqual(len(placement["retained"]), 1)
            self.assertNotIn(placement["affected_copy"], placement["retained"])

    def test_generated_results_match_archived_bytes(self):
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch)
            ablation.write_results(path, path / "figure.tex")
            for name in ("assessment_evidence_basis.json", "assessment_evidence_basis.csv", "stage_ablation.json",
                         "stage_ablation.csv", "stage_ablation_by_domain.csv"):
                self.assertEqual((path / name).read_bytes(), (assessments.OUTPUT / name).read_bytes())
            self.assertEqual((path / "figure.tex").read_text(), ablation.figure(json.loads((path / "stage_ablation.json").read_text())))
