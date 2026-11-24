"""Check formal scope, evidence binding and reproducibility of the six-case audit."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from recovery_experiment.procedure_formalism.paper_v3 import representative as audit


class RepresentativeCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = audit.build_matrix()
        cls.assessments = {a["subcase"]: a for group in cls.matrix["cases"] for a in group["assessments"]}

    def test_outputs_round_trip_and_cite_existing_theorems(self):
        self.assertEqual(len(self.matrix["cases"]), 6)
        self.assertEqual(len(self.assessments), 10)
        self.assertEqual(set(self.assessments), {"M0", "M5", "M13", "H0", "H1", "H2", "MER0", "MER6", "MER10", "CHP0"})
        with TemporaryDirectory() as directory:
            target = Path(directory)
            matrix, doc, table = (target / name for name in ("matrix.json", "audit.md", "table.tex"))
            audit.generate(matrix, doc, table)
            self.assertEqual(matrix.read_bytes(), audit.MATRIX.read_bytes())
            self.assertEqual(doc.read_bytes(), audit.DOC.read_bytes())
            self.assertEqual(table.read_text(), audit.render_table(json.loads(matrix.read_text())))
        for a in self.assessments.values():
            self.assertEqual(set(a["obligations"]), {f"O{i}" for i in range(1, 9)})
            self.assertEqual(a["obligations"]["O8"]["status"], "INAPPLICABLE")
            for ob in a["obligations"].values():
                for theorem in ob["evidence"]["theorems"]:
                    source = a["proof_record"][theorem]
                    for key, digests in (("model", a["model_hash"]), ("record", a["proof_hash"])):
                        self.assertEqual(audit.file_hash(audit.ROOT / source[key]), digests[source[key]])

    def test_adverse_branch_and_incident_integrity_have_distinct_scopes(self):
        for code in ("M5", "M13", "MER6", "MER10"):
            a = self.assessments[code]
            paths = a["finite_model_check"]["terminal_executions"]
            self.assertTrue(all(s["evidence_implies_correspondence"] for s in paths))
            self.assertTrue(any(not s["physical"] and not s["evidence_produced"] for s in paths))
            self.assertEqual([a["obligations"][k]["status"] for k in ("O5", "O6", "O7")], ["REFUTED"] * 3)
            unknown = code in ("M13", "MER10")
            self.assertEqual(a["classification"], "UNKNOWN" if unknown else "REJECTED")
            self.assertEqual(any(s["complete_contract"] for s in paths), code != "MER6")

    def test_service_at_deadline_and_empty_program(self):
        for code in ("M0", "H0", "MER0"):
            a = self.assessments[code]
            for i in range(1, 8):
                self.assertEqual(a["obligations"][f"O{i}"]["status"], "PROVED")
            self.assertTrue(a["obligations"]["O6"]["evidence"]["theorems"][0].endswith("O6_correspondence"))
            self.assertTrue(all(p["complete_contract"] and p["evidence_produced"] and p["evidence_implies_correspondence"]
                                for p in a["finite_model_check"]["terminal_executions"]))
        absent = self.assessments["H1"]
        self.assertEqual(absent["finite_model_check"]["terminal_executions"], [])
        self.assertEqual(absent["obligations"]["O2"]["status"], "REFUTED")
        late = self.assessments["H2"]
        end, = late["finite_model_check"]["terminal_executions"]
        self.assertEqual([end["values"][k] for k in ("tick2", "flow2", "tick3", "flow3")], ["3", "4", "4", "32/5"])
        self.assertTrue(end["physical"] and end["evidence_produced"])
        self.assertFalse(end["on_time"] or end["complete_contract"])
        self.assertEqual(late["obligations"]["O7"]["status"], "REFUTED")

    def test_heartbeat_is_trace_evidence_only(self):
        a = self.assessments["CHP0"]
        self.assertEqual(a["milestones"], {"device": "ESTABLISHED", "process": "UNKNOWN", "customer_service": "UNKNOWN"})
        self.assertEqual(a["obligations_proved"], [])
        self.assertEqual(a["proof_record"], {})
        self.assertEqual(a["obligations"]["O6"]["status"], "UNBOUND_EVIDENCE")
        self.assertEqual(a["obligations"]["O7"]["status"], "UNBOUND_MODEL")
        probe = a["trace_evidence"]["probe"]
        self.assertGreater(probe["scan_count_after"], probe["scan_count_before"])
