import json
import unittest
from dataclasses import replace

from recovery_experiment.procedure_formalism.case_assessment import (
    CHP_GAPS, CHP_WITNESSES, MERWIN_GAPS, MERWIN_WITNESSES, cost_report, schema_assessment,
)
from recovery_experiment.procedure_formalism.cost_vector import (
    CostCandidate, CostComponent, CostContext, Comparison, RecoveryCostVector, Weight,
    pareto_compare, remote_trace_cost, weighted_compare,
)
from recovery_experiment.procedure_formalism.domain_cases import (
    CHP_HOLD, HYDRO_HOLD, LOCAL_AUTO, NO_ASSURANCE, RELOAD, RESET, chp_procedures, merwin_procedures,
)
from recovery_experiment.procedure_formalism.procedure import EvidenceStatus, ProcedureStatus, RecoveryProcedure


class CostContracts(unittest.TestCase):
    def setUp(self):
        def component(value, unit):
            return CostComponent(value, unit, "unit test", 1.0, EvidenceStatus.RESEARCH_AUTHORED)

        context = CostContext("stopped", "nominal", "required service", "sample safety", 1.0, 1.0)
        vector = RecoveryCostVector(
            component(1, "m3"), component(2, "s"), component(3, "person*h"),
            component(4, "count"), component(5, "kWh"), component(6, "s"),
        )
        self.candidate = CostCandidate("test", ProcedureStatus.PROVED, context, vector, True, "d" * 64)

    def test_trace_components_distinguish_unknown_from_zero(self):
        vector = remote_trace_cost()
        self.assertEqual(vector.service_deficit.value, 0.0006)
        self.assertEqual(vector.service_deficit.unit, "m3")
        self.assertEqual(vector.restoration_delay.value, 0.2)
        self.assertEqual(vector.intervention_count.value, 1)
        self.assertEqual(vector.evidence_gap_duration.value, 0)
        self.assertIsNone(vector.resource_use.value)
        self.assertIsNone(vector.human_effort.value)
        for entry in vector.as_dict().values():
            self.assertEqual(entry["measurement_horizon_s"], 0.3)
            self.assertTrue(entry["provenance"])
            self.assertTrue(entry["unit"])

    def test_missing_measurement_is_ineligible_for_complete_pareto_order(self):
        vector = remote_trace_cost()
        context = replace(self.candidate.context, horizon_s=0.3, deadline_s=0.3)
        candidate = replace(self.candidate, context=context, vector=vector)
        self.assertEqual(pareto_compare(candidate, candidate), Comparison.INCOMPLETE)
        self.assertEqual(weighted_compare(candidate, candidate, {"service_deficit": Weight(2, 1, "m3")}), Comparison.TIE)
        self.assertEqual(weighted_compare(candidate, candidate, {"human_effort": Weight(1, 1, "person*h")}), Comparison.INCOMPLETE)

    def test_admission_and_common_scenario_are_mandatory(self):
        a = self.candidate
        for status in (ProcedureStatus.REJECTED, ProcedureStatus.UNKNOWN):
            other = replace(a, status=status)
            self.assertEqual(pareto_compare(a, other), Comparison.NOT_ADMISSIBLE)
            self.assertEqual(weighted_compare(a, other, {}), Comparison.NOT_ADMISSIBLE)
        self.assertEqual(pareto_compare(a, replace(a, provides_required_service=False)), Comparison.NOT_ADMISSIBLE)
        for field in ("initial_state_id", "environment_id", "service_contract", "safety_contract"):
            other = replace(a, context=replace(a.context, **{field: "different"}))
            self.assertEqual(pareto_compare(a, other), Comparison.DIFFERENT_CONTEXT)
        with self.assertRaises(ValueError):
            replace(a, formal_model_sha256=None)
        with self.assertRaises(ValueError):
            replace(a, context=replace(a.context, horizon_s=2.0))
        with self.assertRaises(ValueError):
            replace(a, context=replace(a.context, deadline_s=2.0))

    def test_dominance_tradeoff_and_declared_weights(self):
        a = self.candidate
        more_delay = replace(a.vector.restoration_delay, value=3)
        more_expensive = replace(a, vector=replace(a.vector, restoration_delay=more_delay))
        self.assertEqual(pareto_compare(a, more_expensive), Comparison.LEFT)
        self.assertEqual(pareto_compare(more_expensive, a), Comparison.RIGHT)
        tradeoff = replace(a, vector=replace(more_expensive.vector, resource_use=replace(a.vector.resource_use, value=3)))
        self.assertEqual(pareto_compare(a, tradeoff), Comparison.TRADEOFF)
        self.assertEqual(weighted_compare(a, tradeoff, {
            "restoration_delay": Weight(1, 1, "s"), "resource_use": Weight(1, 1, "kWh"),
        }), Comparison.RIGHT)
        self.assertEqual(weighted_compare(a, tradeoff, {
            "restoration_delay": Weight(3, 1, "s"), "resource_use": Weight(1, 1, "kWh"),
        }), Comparison.LEFT)

    def test_trace_selection_binds_verified_status_hash_context_and_clock(self):
        from recovery_experiment.procedure_formalism.attleboro import attleboro
        from recovery_experiment.procedure_formalism.evaluation import report

        nominal = report(attleboro()["remote"])
        result = cost_report(nominal)
        self.assertEqual(result["eligible_for_cost_comparison"], nominal["result"] == "PROVED")
        self.assertEqual(result["formal_model_sha256"], nominal["formal_model_sha256"])
        self.assertEqual(result["comparison"]["result"], Comparison.DIFFERENT_CONTEXT.value)
        for key, replacement in (("horizon", 4), ("tick_seconds", 1), ("formal_model_sha256", "unsigned"),
                                 ("dependency_states", {}), ("initial_state", {}), ("proof_record", "other")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                cost_report({**nominal, key: replacement})

    def test_units_and_reference_scales_are_checked(self):
        a = self.candidate
        wrong_unit = replace(a.vector.service_deficit, unit="MWh")
        with self.assertRaises(ValueError):
            pareto_compare(a, replace(a, vector=replace(a.vector, service_deficit=wrong_unit)))
        with self.assertRaises(ValueError):
            weighted_compare(a, a, {"resource_use": Weight(1, 1, "m3")})
        with self.assertRaises(ValueError):
            weighted_compare(a, a, {})
        with self.assertRaises(ValueError):
            Weight(1, 0, "s")
        with self.assertRaises(ValueError):
            replace(a.vector.service_deficit, value=None)
        with self.assertRaises(ValueError):
            replace(a.vector.service_deficit, value=float("nan"))


class DomainAssessments(unittest.TestCase):
    def test_merwin_modes_and_source_scope(self):
        procedures = merwin_procedures()
        self.assertEqual(len(procedures), 4)
        manual, auto, hcc, hold = procedures
        self.assertTrue(all(isinstance(p, RecoveryProcedure) for p in procedures))
        self.assertIs(manual.required_dependencies["breaker"], hcc.required_dependencies["breaker"])
        self.assertIn("lube", manual.required_dependencies)
        self.assertIn("lube", auto.required_dependencies)
        self.assertIn("auxiliaries", hcc.required_dependencies)
        self.assertIn("hcc_link", hcc.required_dependencies)
        self.assertNotIn("hcc_link", auto.required_dependencies)
        self.assertNotEqual(manual.controller_transition, auto.controller_transition)
        self.assertIsNone(hold.actuator)
        report = schema_assessment(procedures, "pinned-tree", MERWIN_GAPS, MERWIN_WITNESSES)
        rows = {row["procedure_id"]: row for row in report["procedures"]}
        self.assertEqual(rows[LOCAL_AUTO]["result"], "UNKNOWN")
        self.assertIsNone(rows[LOCAL_AUTO]["proof_record"])
        self.assertEqual(rows[HYDRO_HOLD]["service_status"], "NO_POSITIVE_SERVICE_CLAIM")
        json.dumps(report)

    def test_chp_device_echo_does_not_establish_process_or_customer_service(self):
        procedures = chp_procedures()
        self.assertEqual(len(procedures), 4)
        self.assertTrue(all(isinstance(p, RecoveryProcedure) and p.plant_model is None for p in procedures))
        report = schema_assessment(procedures, "pinned-tree", CHP_GAPS, CHP_WITNESSES)
        rows = {row["procedure_id"]: row for row in report["procedures"]}
        self.assertEqual(rows[RESET]["device_logic_execution"], "NOT_ESTABLISHED")
        self.assertEqual(rows[RELOAD]["device_logic_execution"], "OBSERVED_ON_DISPOSABLE_RUNTIME")
        self.assertEqual(rows[CHP_HOLD]["service_status"], "NO_POSITIVE_SERVICE_CLAIM")
        self.assertEqual(rows[NO_ASSURANCE]["portfolio_outcome"], "NO_ASSURED_PROCESS_RECOVERY")
        for row in rows.values():
            for field in ("result", "process_readiness", "physical_chp_output", "customer_service"):
                self.assertEqual(row[field], "UNKNOWN")
            self.assertIsNone(row["proof_record"])
