"""Compare the sensitivity results with the fixed archives and boundary arithmetic."""

import json
import unittest
from fractions import Fraction

from recovery_experiment.procedure_formalism.paper_v5 import regions


class WaterRegionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = regions.water_report()

    def test_whole_grid_matches_symbolic_region(self):
        rows = self.report["results"]
        self.assertEqual(len(rows), 4 * 4 * 3 * 4)
        for row in rows:
            with self.subTest(row=row):
                n, r = row["mandatory_scans"], row["ready_tick"]
                if n > 3:
                    self.assertEqual(row["result"], regions.UNSUPPORTED)
                    self.assertIsNone(row["flow_lps"])
                elif row["case"] == "H1":
                    self.assertEqual(row["result"], "PREMISE_INAPPLICABLE")
                    self.assertIsNone(row["terminal_tick"])
                else:
                    q = 10 * (1 - Fraction(3, 5) ** (n - 1))
                    self.assertEqual(Fraction(row["flow_lps"]), q)
                    self.assertEqual(Fraction(row["pressure_psi"]), 30 + 3 * q)
                    self.assertEqual(row["terminal_tick"], r + n)
                    self.assertTrue(row["fresh_matching_reading"] and row["safe"])
                    on_time = r + n <= row["deadline_tick"] and q >= Fraction(row["minimum_flow_lps"])
                    self.assertEqual(row["result"], regions.CHECKED if on_time else regions.VIOLATED)

    def test_original_three_scan_decisions_and_witnesses(self):
        rows = {row["case"]: row for row in self.report["results"] if
                (row["mandatory_scans"], row["deadline_tick"], row["minimum_flow_lps"]) == (3, 3, "5")}
        saved = json.loads((regions.ROOT / "results/attleboro_positive.json").read_text())
        nominal = rows["M0"]
        self.assertEqual(nominal["result"], regions.CHECKED)
        self.assertEqual(Fraction(nominal["flow_lps"]), Fraction(saved["execution_witness"]["q"]))
        hand = json.loads((regions.ROOT / "results/milestone2/attleboro_hand_mutations.json").read_text())
        for row in hand["rows"][:3]:
            derived = rows[row["scenario"]]
            self.assertEqual(derived["result"] == regions.CHECKED, row["B4"] == "PROVED")
            if row["reachable_terminal_states"]:
                self.assertEqual(derived["terminal_tick"], row["witness"]["t"])
                self.assertEqual(Fraction(derived["pressure_psi"]), Fraction(row["witness"]["pressure"]))


class HydroRegionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = regions.hydro_report()

    def test_limits_match_exact_archived_samples_and_poll_count(self):
        nominal, = self.report["branches"]["MER0"]
        archive = json.loads((regions.ROOT / "results/milestone2/merwin_mutations.json").read_text())
        source = next(r for r in archive["rows"] if r["scenario"] == "MER0")["execution"]
        self.assertEqual(nominal["generation_mw"], [source[f"mw{i}"] for i in (1, 2, 3)])
        self.assertEqual(nominal["ticks"], [1285, 1291, 1296])
        for row in self.report["results"]:
            k = row["required_polls"]
            with self.subTest(row=row):
                if k == 4:
                    self.assertEqual(row["result"], regions.UNSUPPORTED)
                elif row["case"] == "MER0" and row["result"] == regions.CHECKED:
                    highest = min(Fraction(x) for x in nominal["generation_mw"][-k:])
                    self.assertEqual(Fraction(row["maximum_mw_inclusive"]), highest)

    def test_unknown_contact_stale_meter_and_open_contact(self):
        states = self.report["branches"]
        self.assertEqual({tuple(s["generation_mw"]) for s in states["MER10"]},
                         {tuple(states["MER0"][0]["generation_mw"]), ("0", "0", "0")})
        self.assertEqual(states["MER6"][0]["contact"], 0)
        self.assertEqual(states["MER8"][0]["fresh"], [1, 1, 0])
        for k in (1, 2, 3):
            rows = [r for r in self.report["results"] if r["required_polls"] == k]
            nominal, = (r for r in rows if r["case"] == "MER0" and r["result"] == regions.CHECKED)
            uncertain, = (r for r in rows if r["result"] == "UNKNOWN_CONTACT_INTEGRITY")
            over, = (r for r in rows if r["case"] == "MER10" and r["result"] == "SERVICE_CONTRACT_VIOLATED")
            self.assertEqual(uncertain["maximum_mw_inclusive"], nominal["maximum_mw_inclusive"])
            self.assertEqual(over["minimum_mw_exclusive"], nominal["maximum_mw_inclusive"])
            for r in rows:
                if r["case"] in ("MER6", "MER8"):
                    self.assertEqual(r["result"], "SERVICE_CONTRACT_VIOLATED")
                    self.assertIsNone(r["maximum_mw_inclusive"])
