"""Check replay of the serialized archive timing protocol without launching Java."""

import csv
import json
from pathlib import Path
import random
import tempfile
import unittest

from recovery_experiment.procedure_formalism.paper_v2 import proof_timing as timing


class ProofTimingTests(unittest.TestCase):
    def write_round(self, raw, order):
        with raw.open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=timing.FIELDS)
            writer.writeheader()
            for index, case in enumerate(order, 1):
                count = len(timing.expected_exports(case))
                writer.writerow(dict(case=case, round=1, order=1 if case == "game" else index, obligations=count,
                                     proved=count, setup_ms=5, tactic_ms=4, wall_ms=10,
                                     composition_ms="" if case == "game" else 1, exports_match=1, return_code=0,
                                     restricted_optional_lemmas=1, status="PROVED"))

    def test_summarize_checks_run_order_and_preserves_one_sample_per_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "observations.csv"
            report = Path(directory) / "report.json"
            order = list(timing.FIXED)
            random.Random(timing.SEED).shuffle(order)
            order.append("game")
            self.write_round(raw, order)
            timing.summarize(raw, report)
            result = json.loads(report.read_text())
            self.assertEqual(result["rounds"], 1)
            self.assertEqual(result["runs"], 6)
            self.assertEqual(result["cases"]["remote"]["wall_ms"]["median"], 10)
            self.assertEqual(result["raw_sha256"], timing.digest(raw))
            self.write_round(raw, list(reversed(order)))
            with self.assertRaisesRegex(ValueError, "incomplete or out of order"):
                timing.summarize(raw, report)

    def test_ten_repetition_median_and_nearest_rank_p95(self):
        self.assertEqual(timing.distribution(range(1, 11)), {
            "median": 5.5, "p95": 10, "min": 1, "max": 10})
