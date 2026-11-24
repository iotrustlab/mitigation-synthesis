"""Source-guard, bounded plant and evidence checks for the HCC research fixture."""

import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from recovery_experiment.procedure_formalism.domain_cases import HYDRO_HOLD, LOCAL_AUTO, LOCAL_MANUAL
from recovery_experiment.procedure_formalism.formal_ir import executions
from recovery_experiment.procedure_formalism.milestone2 import merwin as hydro
from recovery_experiment.procedure_formalism.milestone2 import merwin_reduction as plant


class MerwinResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = hydro.reports()["merwin_mutations"]["rows"]

    def test_source_modes_and_shared_unit(self):
        modes = {p.procedure_id: p for p in hydro.candidates(hydro.CASES[0])}
        self.assertEqual(set(modes), {LOCAL_MANUAL, LOCAL_AUTO, hydro.ID, HYDRO_HOLD})
        unit = modes[hydro.ID].required_dependencies["hydro_unit"]
        for mode in (LOCAL_AUTO, LOCAL_MANUAL):
            self.assertIs(modes[mode].required_dependencies["hydro_unit"], unit)

    def test_nominal_end_to_end_and_progress(self):
        _, initial, stages = hydro.model(0)
        states = executions(stages, initial)
        self.assertEqual(len(states), 1)
        state = states[0]
        self.assertLess(state["requestClock"], state["settleClock"])
        self.assertLess(state["settleClock"], state["syncClock"])
        self.assertEqual(state["timerMs"], 100)
        self.assertEqual(state["terminalSpeed"], 100 * plant.S)
        self.assertLessEqual(state["contactClock"], state["tick1"])
        self.assertLess(state["tick1"], state["tick2"])
        self.assertLess(state["tick2"], state["tick3"])
        for i in range(1, 4):
            self.assertGreaterEqual(state[f"mw{i}"], 1)
            self.assertEqual(state[f"observed{i}"], state[f"mw{i}"])
        self.assertEqual(self.rows[0]["B4"], "PROVED")
        self.assertTrue(hydro.proved(hydro.profile(0)))

    def test_actor_link_auxiliary_and_lubrication_guard(self):
        self.assertEqual(self.rows[9]["B3"], "ACCEPT")  # Controller inputs still indicate speed.
        self.assertEqual(self.rows[9]["B4"], "REJECTED")  # The actual hydro unit is unavailable.
        for i in (1, 2, 4):
            self.assertEqual(self.rows[i]["B4"], "REJECTED")
            self.assertEqual(self.rows[i]["B3"], "DECLINE")
        modes = {p.procedure_id: p for p in hydro.candidates(hydro.CASES[3])}
        self.assertNotIn("lube", modes[hydro.ID].required_dependencies)
        self.assertEqual(modes[LOCAL_MANUAL].required_dependencies["lube"].status, hydro.D.UNAVAILABLE)
        self.assertEqual(self.rows[3]["B4"], "PROVED")
        self.assertEqual(hydro.profile(0).sha256, hydro.profile(3).sha256)
        self.assertEqual(self.rows[4]["execution"]["mw1"], "0")

    def test_sync_contact_generation_and_observation(self):
        for case, values in (
            (5, ("0", "0", "0", "0")),
            (6, ("1", "0", "0", "0")),
            (7, ("1", "1", "0", "0")),
            (8, ("1", "1", "1", "0")),
        ):
            with self.subTest(case=case):
                self.assertEqual(self.rows[case]["B4"], "REJECTED")
                witness = self.rows[case]["execution"]
                self.assertEqual(
                    tuple(witness[k] for k in ("closeCmd", "contact", "service", "credible")), values
                )
        self.assertEqual(self.rows[9]["B1"], "DECLINE")

    def test_unknown_integrity_has_a_conditional_counterexample(self):
        _, initial, stages = hydro.model(10)
        self.assertEqual({s["service"] for s in executions(stages, initial)}, {0, 1})
        self.assertEqual(self.rows[10]["B4"], "UNKNOWN")
        self.assertTrue(hydro.proved(hydro.profile(10)))

    def test_certificate_and_forcing_columns(self):
        with plant.FIXTURE.open() as src:
            self.assertEqual(tuple(csv.DictReader(src).fieldnames), plant.CSV_FIELDS)
        _, facts = plant.trajectory()
        self.assertEqual(facts["horizon_ticks"], 1296)
        self.assertEqual(facts["settled_tick"], 652)
        self.assertEqual(facts["service_ticks"], [1285, 1291, 1296])
        self.assertTrue(plant.checked_reduction())
        with tempfile.TemporaryDirectory() as scratch, patch.object(
            plant, "RECORD", Path(scratch) / "missing.json"
        ):
            self.assertFalse(plant.checked_reduction())
            self.assertEqual(hydro._report(0, False)["B4"], "UNKNOWN")
