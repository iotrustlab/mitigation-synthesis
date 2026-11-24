"""The adaptive proof and latency distributions must remain bound to their raw inputs."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from recovery_experiment.procedure_formalism.paper_v2 import game, scaling


class AdaptiveGameTests(unittest.TestCase):
    def test_game_proofs_and_reference_counterstrategy(self):
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / "game.json"
            game.report(game.EVIDENCE, report)
            self.assertEqual(report.read_bytes(), (scaling.DEFAULT_OUTPUT / "adaptive_game.json").read_bytes())
            data = json.loads(report.read_text())
        policy = {tuple(r["observed"]): r for r in data["strategy_table"]}
        self.assertEqual(policy[0, 0]["legal_actions"], ["hold"])
        self.assertEqual(policy[0, 0]["winning_actions"], [])
        self.assertEqual(policy[0, 1]["winning_actions"], ["P3"])
        self.assertEqual(policy[1, 0]["winning_actions"], ["P2"])
        self.assertEqual(policy[1, 1]["winning_actions"], ["P2", "P3"])

    def test_mismatched_game_export_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "evidence"
            shutil.copytree(game.EVIDENCE, root)
            witness = root / "proof_records/water_game/shared_power_no_win.kyp"
            witness.write_bytes((witness.parent / "adaptive_win.kyp").read_bytes())
            with self.assertRaisesRegex(ValueError, "shared_power_no_win"):
                game.report(root, Path(temp) / "game.json")


class DependencyScalingTests(unittest.TestCase):
    def test_distributions_are_reproducible_from_complete_schedule(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copy(scaling.DEFAULT_OUTPUT / scaling.RAW, root)
            scaling.report(root)
            self.assertEqual((root / scaling.SUMMARY).read_bytes(), (scaling.DEFAULT_OUTPUT / scaling.SUMMARY).read_bytes())
            # Dropping just one final RSS probe invalidates the schedule even
            # though the primary latency statistics would be unchanged.
            raw = (root / scaling.RAW).read_text().splitlines(keepends=True)
            (root / scaling.RAW).write_text("".join(raw[:-1]))
            with self.assertRaises(ValueError):
                scaling.report(root)

    def test_quantiles_and_independent_oracle(self):
        summary = scaling.summarize(list(reversed(range(1, 31))))
        self.assertEqual(summary["median"], 15.5)
        self.assertEqual(summary["p95"], 29)
        self.assertEqual(summary["median_order_interval"], [10, 21])
        cells = json.loads((scaling.DEFAULT_OUTPUT / scaling.SUMMARY).read_text())["cells"]
        mixed = next(r for r in cells if len(set(r["expected_verdicts"])) == 2)
        self.assertEqual(mixed["actual_fanout"], 1)
        self.assertIn("SU", mixed["expected_solver_answers"])
        self.assertIn("SS", mixed["expected_solver_answers"])
