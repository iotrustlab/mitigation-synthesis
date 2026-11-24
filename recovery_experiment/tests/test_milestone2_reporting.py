"""The factorial benchmark and catalog retain bound procedure semantics."""
import json
from pathlib import Path
import tempfile
import unittest

from recovery_experiment.procedure_formalism.milestone2 import proofs, reports, scalability as scale
from recovery_experiment.procedure_formalism.procedure import DependencyStatus


class Milestone2ReportingTests(unittest.TestCase):
    def test_shared_fanout_and_identity(self):
        resources, candidates = scale.structure(16, 4, 25, "high")
        self.assertEqual(sum(n.status == DependencyStatus.COMPROMISED for n in resources.values()), 4)
        for p in candidates:
            self.assertIs(p.required_dependencies["d0"], resources["d0"])
        low, plans = scale.structure(16, 4, 25, "low")
        self.assertFalse(set(plans[0].required_dependencies) & set(plans[1].required_dependencies))
        self.assertEqual(sum(len(p.required_dependencies) for p in plans), len(low))

    def test_scale_counts_and_determinism(self):
        for n,k,pct,level in ((8,1,0,"low"),(16,2,10,"medium"),(32,4,25,"medium"),(64,8,50,"high")):
            data, stats=scale.encode(*scale.structure(n,k,pct,level))
            self.assertEqual(data,scale.encode(*scale.structure(n,k,pct,level))[0])
            self.assertEqual(data.count(b"(check-sat)"),2*k)
            self.assertEqual(stats["joint_branch_count"],2**((n*pct+50)//100))
            self.assertTrue(all(v<=stats["joint_branch_count"] for v in stats["candidate_branch_counts"]))

    def test_incomplete_solver_evidence(self):
        self.assertEqual(scale.decisions(["sat","unsat","sat","sat"],2),["PROVED","REJECTED"])
        self.assertEqual(scale.decisions(["sat","unknown"],1),["UNKNOWN"])
        self.assertEqual(scale.decisions(["timeout"],2),["UNKNOWN","UNKNOWN"])

    def test_factorial_coverage_and_outcomes(self):
        record=scale.report()
        self.assertEqual(len(record["rows"]),192)
        for row in record["rows"]:
            if row["return_code"] == 0 and "unknown" not in row["solver_answers"] and "timeout" not in row["solver_answers"]:
                self.assertEqual(row["outcomes"],["PROVED" if k==1 else "REJECTED" for k in row["candidate_branch_counts"]])

    def test_checked_catalog_and_reproduction(self):
        with tempfile.TemporaryDirectory() as scratch:
            folder=Path(scratch)
            reports.generate(folder)
            files=sorted(folder.glob("*.json"))
            self.assertEqual(len(files),17)
            for f in files:
                self.assertEqual(f.read_bytes(),(proofs.RESULTS/f.name).read_bytes(),f.name)
                obj=json.loads(f.read_text())
                self.assertTrue({"source_commit","formal_model_sha256","proof_profile_sha256",
                                 "timestamp","tool_versions","configuration"} <= obj.keys())
            counts=json.loads((folder/"rq1_summary.json").read_text())["overall"]
            self.assertEqual(counts["procedure_assessments"], sum(counts["end_to_end"].values()))
            self.assertEqual(counts["scenarios"],54)

    def test_proof_reader_rejects_unbound_tactic(self):
        from recovery_experiment.procedure_formalism.milestone2.hand import profiles
        from dataclasses import replace
        profile=profiles()[0]
        self.assertTrue(proofs.proved(profile))
        changed=replace(profile,obligations=(replace(profile.obligations[0],tactic="skip"),*profile.obligations[1:]))
        self.assertFalse(proofs.proved(changed))
