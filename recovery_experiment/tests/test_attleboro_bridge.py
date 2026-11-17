"""Focused checks for the source-bound Attleboro trace correspondence gate."""

from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from recovery_experiment.attleboro.bridge import REQUIRED_TAGS, inspect_bundle


class AttleboroBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / "runs" / "case"
        self.bundle.mkdir(parents=True)
        self.controller = self.root / "implementations/openplc/st/attleboro_controller.st"
        self.simulator = self.root / "implementations/openplc/st/attleboro_simulator.st"
        self.contract = self.root / "tag_contract.yaml"
        self.backend_map = self.root / "implementations/openplc/configs/openplc_map.yaml"
        self.scenarios = self.root / "scenarios/cases.yaml"
        self.reference_core = self.root / "model/core.py"
        self.reference_runner = self.root / "model/run.py"
        self.live_driver = self.root / "model/live.py"
        self.controller.parent.mkdir(parents=True)
        self.backend_map.parent.mkdir(parents=True)
        self.scenarios.parent.mkdir(parents=True)
        self.reference_core.parent.mkdir(parents=True)
        self.controller.write_text("controller fixture\n")
        self.simulator.write_text("simulator fixture\n")
        self.contract.write_text("contract fixture\n")
        self.backend_map.write_text("map fixture\n")
        self.scenarios.write_text("scenarios fixture\n")
        self.reference_core.write_text("reference model fixture\n")
        self.reference_runner.write_text("reference runner fixture\n")
        self.live_driver.write_text("live driver fixture\n")

    def _row(self, **changes: str) -> dict[str, str]:
        row = {tag: "0" for tag in REQUIRED_TAGS}
        row.update({
            "ATT_Utility_Available": "1",
            "ATT_Selector_Remote": "1",
            "ATT_SCADA_Start_Request": "1",
            "ATT_Remote_Eligible": "1",
            "ATT_Remote_Start": "1",
        })
        row.update(changes)
        return row

    def _write(self, rows: list[dict[str, str]], backend: str, scenario: str = "case") -> None:
        hashes = {
            "controller_st": hashlib.sha256(self.controller.read_bytes()).hexdigest(),
            "simulator_st": hashlib.sha256(self.simulator.read_bytes()).hexdigest(),
            "tag_contract": hashlib.sha256(self.contract.read_bytes()).hexdigest(),
            "backend_map": hashlib.sha256(self.backend_map.read_bytes()).hexdigest(),
            "scenario_set": hashlib.sha256(self.scenarios.read_bytes()).hexdigest(),
        }
        if backend == "synthetic":
            hashes.update({
                "reference_core": hashlib.sha256(self.reference_core.read_bytes()).hexdigest(),
                "reference_runner": hashlib.sha256(self.reference_runner.read_bytes()).hexdigest(),
            })
        else:
            hashes["live_driver"] = hashlib.sha256(self.live_driver.read_bytes()).hexdigest()
        (self.bundle / "meta.json").write_text(json.dumps({
            "artifact_sha256": hashes,
            "backend_type": backend,
            "contract_version": "0.1.0",
            "scenario": scenario,
            "usecase_id": "attleboro-interconnection-2019-design-slice",
        }))
        fields = sorted(set().union(*(row.keys() for row in rows)))
        with (self.bundle / "tags.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_synthetic_latch_and_return_without_reset(self) -> None:
        self._write([
            self._row(ATT_Utility_Available="0", ATT_MTS_Generator="1",
                      ATT_Reset_Request="1", ATT_Reset_Pending="1",
                      ATT_Remote_Eligible="0", ATT_Remote_Start="0"),
            self._row(ATT_Reset_Request="1", ATT_Reset_Pending="1",
                      ATT_Remote_Eligible="0", ATT_Remote_Start="0"),
            self._row(ATT_Reset_Pending="1", ATT_Remote_Eligible="0",
                      ATT_Remote_Start="0"),
        ], "synthetic")
        result = inspect_bundle(self.root, self.bundle)
        self.assertEqual(result.status, "MATCHED")
        self.assertEqual(result.checked_latch_transitions, 3)
        self.assertEqual(result.checked_start_transitions, 3)
        self.assertEqual(result.restored_pending_rows, 1)

    def test_momentary_start_seals_after_feedback(self) -> None:
        self._write([
            self._row(ATT_SCADA_Start_Request="1", ATT_Run_FB="0"),
            self._row(ATT_SCADA_Start_Request="0", ATT_Run_FB="1"),
            self._row(ATT_SCADA_Start_Request="0", ATT_Run_FB="1"),
        ], "synthetic")
        result = inspect_bundle(self.root, self.bundle)
        self.assertEqual(result.status, "MATCHED")
        self.assertEqual(result.checked_start_transitions, 3)

    def test_unconfirmed_start_times_out_after_fifty_scans(self) -> None:
        rows = [self._row(ATT_SCADA_Start_Request="1")]
        rows.extend(self._row(ATT_SCADA_Start_Request="0") for _ in range(48))
        rows.append(self._row(ATT_SCADA_Start_Request="0", ATT_Remote_Start="0"))
        self._write(rows, "synthetic")
        self.assertEqual(inspect_bundle(self.root, self.bundle).status, "MATCHED")

    def test_nominal_requires_actual_service_witness(self) -> None:
        self._write([self._row() for _ in range(8)], "openplc", "nominal_remote")
        result = inspect_bundle(self.root, self.bundle)
        self.assertEqual(result.status, "MISMATCH")
        self.assertTrue(any("no actual-service witness" in issue
                            for issue in result.mismatches))

    def test_generator_remote_bypass_is_detected(self) -> None:
        self._write([
            self._row(ATT_Utility_Available="0", ATT_MTS_Generator="1",
                      ATT_Reset_Pending="1", ATT_Remote_Eligible="1"),
        ], "synthetic")
        result = inspect_bundle(self.root, self.bundle)
        self.assertEqual(result.status, "MISMATCH")
        self.assertTrue(any("remote eligibility" in issue for issue in result.mismatches))

    def test_live_startup_latch_is_observed_without_invented_initial_state(self) -> None:
        self._write([
            self._row(ATT_Reset_Pending="1", ATT_Remote_Eligible="0",
                      ATT_Remote_Start="0", ATT_Delivered_Remote_Start="1"),
        ], "openplc")
        result = inspect_bundle(self.root, self.bundle)
        self.assertEqual(result.status, "MATCHED")
        self.assertEqual(result.checked_latch_transitions, 0)
        self.assertEqual(result.delivery_difference_rows, 1)
        self.assertEqual(result.adversarial_bypass_rows, 0)
        self.assertIn("prior startup scans", result.initial_latch_basis)

    def test_live_remote_start_requires_eligibility(self) -> None:
        self._write([
            self._row(ATT_Reset_Pending="1", ATT_Remote_Eligible="0",
                      ATT_Remote_Start="1"),
        ], "openplc")
        result = inspect_bundle(self.root, self.bundle)
        self.assertEqual(result.status, "MISMATCH")
        self.assertTrue(any("bypasses controller eligibility" in issue
                            for issue in result.mismatches))

    def test_only_adversarial_fixture_counts_as_bypass(self) -> None:
        self._write([
            self._row(ATT_Reset_Pending="1", ATT_Remote_Eligible="0",
                      ATT_Remote_Start="0", ATT_Delivered_Remote_Start="1"),
        ], "openplc", "adversarial_scada_compromised")
        result = inspect_bundle(self.root, self.bundle)
        self.assertEqual(result.status, "MATCHED")
        self.assertEqual(result.delivery_difference_rows, 1)
        self.assertEqual(result.adversarial_bypass_rows, 1)

    def test_changed_controller_source_is_rejected(self) -> None:
        self._write([self._row()], "synthetic")
        self.controller.write_text("changed controller\n")
        with self.assertRaisesRegex(ValueError, "source binding changed"):
            inspect_bundle(self.root, self.bundle)


if __name__ == "__main__":
    unittest.main()
