"""Tests of local water recovery and evidence-limited CHP decisions."""

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from recovery_experiment.procedure_formalism.attleboro import attleboro
from recovery_experiment.procedure_formalism.evaluation import HAND_STATE
from recovery_experiment.procedure_formalism.formal_model import build_model
from recovery_experiment.procedure_formalism.milestone2 import chp, hand
from recovery_experiment.procedure_formalism.procedure import DependencyStatus as DS


class HandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = hand.reports()
        cls.rows = {r["scenario"]: r for r in cls.data["attleboro_hand_mutations"]["rows"]}

    def test_actor_and_panel_path(self):
        row = self.rows["H0"]
        self.assertEqual(row["B4"], "PROVED")
        self.assertEqual(row["witness"]["q"], "32/5")
        self.assertEqual(row["witness"]["t"], 3)
        self.assertEqual((row["witness"]["safe"], row["witness"]["established"]), (1, 1))
        self.assertNotIn("plc", row["dependency_states"])
        self.assertEqual(row["B3"], "INAPPLICABLE")

    def test_required_dependencies_disable_guard(self):
        for case, key in (("H1", "local_operator"), ("H4", "vfd"), ("H5", "pump"), ("H10", "motor_power")):
            with self.subTest(case=case):
                row = self.rows[case]
                self.assertEqual(row["B4"], "REJECTED")
                self.assertEqual(row["dependency_states"][key], "UNAVAILABLE")
                self.assertEqual(row["reachable_terminal_states"], 0)
                self.assertIsNone(row["witness"])

    def test_access_authority_and_ready_time(self):
        inaccessible = attleboro({"hand_panel": DS.UNAVAILABLE}, HAND_STATE)["hand"]
        self.assertEqual(build_model(inaccessible).executions(), [])
        unauthorized = attleboro(initial_state={**HAND_STATE, "authorized": 0})["hand"]
        self.assertEqual(build_model(unauthorized).executions()[0]["accepted"], 0)
        self.assertEqual(self.rows["H2"]["witness"]["t"], 4)
        self.assertIn("DEADLINE_MISSED", self.rows["H2"]["failure_reasons"])
        self.assertEqual(self.rows["H3"]["witness"]["accepted"], 0)
        self.assertEqual(self.rows["H3"]["B4"], "REJECTED")

    def test_trip_no_flow_and_observation(self):
        self.assertEqual(self.rows["H6"]["safety"], "VIOLATED")
        blocked = self.rows["H7"]["witness"]
        self.assertEqual((blocked["run"], blocked["physical"]), (1, 0))
        for key in ("H8", "H9"):
            self.assertEqual(self.rows[key]["witness"]["physical"], 1)
            self.assertEqual(self.rows[key]["observation"], "VIOLATED")
        self.assertEqual(self.rows["H8"]["witness"]["fresh"], 0)
        self.assertEqual(self.rows["H9"]["witness"]["trusted"], 0)

    def test_profile_binding_and_nonvacuity(self):
        positive, diagnostics, overlap = hand.profiles()
        for profile, n in ((positive, 8), (diagnostics, 10), (overlap, 1)):
            self.assertTrue(hand.proved(profile))
            self.assertEqual(len(profile.obligations), n)
        names = {o.name for o in positive.obligations}
        self.assertTrue({"end_to_end", "execution_witness", "precondition_witness"} <= names)
        with patch.object(hand, "proved", return_value=False):
            self.assertEqual(hand.reports()["attleboro_hand_proof_summary"]["result"], "UNKNOWN")

    def test_selector_projection_and_common_hardware(self):
        overlap = self.data["attleboro_domain_overlap"]
        self.assertTrue(overlap["same_shared_objects"])
        self.assertEqual(overlap["domain_remote"]["necessary_selector_pairs"], [(1, 0)])
        self.assertEqual(overlap["domain_hand"]["necessary_selector_pairs"], [(0, 1)])
        self.assertEqual(overlap["intersection_proof"], "PROVED_DISJOINT")
        self.assertFalse(overlap["intersection_satisfiable"])
        self.assertEqual(overlap["cost_comparison"], "NOT_COMPARABLE_UNDER_COMMON_CONTEXT")


class ChpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = chp.reports()["chp_fail_closed_results"]
        cls.rows = {r["scenario"]: r for r in report["rows"]}
        cls.bundles = json.loads(chp.EVIDENCE.read_text())["bundles"]

    def test_benign_logic_witness_and_device_qualification(self):
        nominal = self.rows["CHP0"]
        self.assertEqual(nominal["published_device_lifecycle_assessment"], "SIMULATED")
        self.assertEqual(nominal["published_benign_runtime_assessment"], "EXECUTED")
        self.assertEqual(nominal["device_recovery"], "ESTABLISHED")
        self.assertEqual(nominal["process_recovery"], "UNKNOWN")
        self.assertEqual(nominal["customer_service"], "UNKNOWN")

    def test_backup_constraints_and_bootability(self):
        for key, expected in (("CHP1", "backup_absent"), ("CHP2", "backup_incompatible"),
                              ("CHP3", "backup_provenance_unresolved"), ("CHP4", "device_not_bootable")):
            with self.subTest(case=key):
                self.assertEqual(self.rows[key]["reason"], expected)
                self.assertEqual(self.rows[key]["B4"], "REJECTED")
                self.assertEqual(self.rows[key]["B3"], "DECLINE")
        self.assertFalse(self.rows["CHP4"]["milestones"]["bootable_after_reset"])

    def test_process_permissive_and_customer_evidence_separate(self):
        self.assertEqual(self.rows["CHP5"]["process_recovery"], "UNKNOWN")
        unready = self.rows["CHP6"]
        self.assertEqual(unready["B3"], "ACCEPT")
        self.assertEqual(unready["B4"], "REJECTED")
        self.assertEqual(unready["customer_service"], "UNKNOWN")
        self.assertEqual(self.rows["CHP7"]["reason"], "CUSTOMER_SUPPLY_MECHANISM_UNKNOWN")
        self.assertEqual(self.rows["CHP8"]["cyber_trust"], "UNKNOWN")
        self.assertTrue(all(row["service"] == "UNKNOWN" for row in self.rows.values()))

    def test_heartbeat_needs_two_distinct_reads(self):
        evidence = deepcopy(self.bundles[chp.NOMINAL])
        evidence["probe"]["scan_count_after"] = evidence["probe"]["scan_count_before"]
        row = chp._assess(0, "Compatibility", chp.NOMINAL, evidence)
        self.assertEqual(row["B3"], "UNRESOLVED")
        self.assertNotEqual(row["device_recovery"], "ESTABLISHED")
        self.assertEqual(row["B4"], "UNKNOWN")
