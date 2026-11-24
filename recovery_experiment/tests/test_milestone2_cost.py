"""The controlled benchmark admits and compares procedures in one incident."""

from dataclasses import replace
from fractions import Fraction
import unittest
from unittest.mock import patch

from recovery_experiment.procedure_formalism.milestone2 import cost
from recovery_experiment.procedure_formalism.milestone2.proofs import proved


class ControlledCostTests(unittest.TestCase):
    def test_context_and_shared_topology(self):
        a, b = cost.plans(cost.Context())
        self.assertIs(a.context, b.context)
        self.assertEqual(a.procedure.initial_state, b.procedure.initial_state)
        self.assertEqual(a.procedure.service_definition, b.procedure.service_definition)
        self.assertEqual(a.procedure.safety_definition, b.procedure.safety_definition)
        for key in cost.SHARED:
            self.assertIs(a.procedure.required_dependencies[key], b.procedure.required_dependencies[key])

    def test_mismatched_admission_contexts_rejected(self):
        context = cost.Context()
        a = cost.plans(context)[0]
        for changed in ({"initial_volume": 10}, {"horizon": 5}, {"lower": 3}, {"minimum": 1},
                        {"deadline": 3}, {"demand": 4}, {"auto_capacity": 2}, {"manual_delay": 1},
                        {"faults": (("local_actor", cost.D.UNAVAILABLE),)}):
            with self.subTest(changed=changed):
                b = cost.plans(replace(context, **changed))[1]
                with self.assertRaises(ValueError):
                    cost.certified_selection((a, b), (1, 1, 1, 1))

    def test_cannot_substitute_results_or_contract_in_a_plan(self):
        a, b = cost.plans(cost.Context())
        for incorrect in (replace(b, initial=dict(b.initial, capacity=4)),
                          replace(b, procedure=replace(b.procedure, service_definition="weakened"))):
            with self.assertRaises(ValueError):
                cost.certified_selection((a, incorrect), (1, 1, 1, 1))

    def test_all_formal_profiles_are_checked(self):
        profiles = cost.profiles()
        self.assertEqual(len(profiles), 7)
        self.assertTrue(all(proved(p) for p in profiles))
        self.assertEqual(sum(len(p.obligations) for p in profiles), 19)

    def test_cost_integrals_and_symbolic_weight_identity(self):
        for scenario, expected in {"C0": ((3, 1, 0, 12), (6, 2, 1, 2)),
                                   "C5": ((6, 1, 0, 12), (6, 2, 1, 2))}.items():
            for plan, vector in zip(cost.plans(cost.SCENARIOS[scenario]), expected):
                self.assertEqual(plan.cost_coefficients(), vector)
                w = (Fraction(1, 2), Fraction(2, 3), 0, 3)
                init = {**plan.initial, **dict(zip(cost.WEIGHTS, w))}
                for state in cost.executions(plan.stages, init):
                    self.assertEqual(tuple(state[c] for c in cost.COSTS), vector)
                    self.assertEqual(state["J"], sum(wn * x for wn, x in zip(w, vector)))

    def test_safety_and_service_even_if_cost_weights_are_zero(self):
        for i, expected in enumerate(((cost.A_ID, cost.B_ID), (cost.B_ID,), (cost.A_ID,), (), (),
                                      (cost.A_ID, cost.B_ID), (cost.A_ID,), ())):
            plans = cost.plans(cost.SCENARIOS[f"C{i}"])
            winners = cost.certified_selection(plans, (0, 0, 0, 0))
            self.assertCountEqual(winners["winners"], expected)
            self.assertCountEqual(winners["cost_by_admissible_procedure"], expected)

    def test_weight_policy_and_pareto(self):
        plans = cost.plans(cost.SCENARIOS["C0"])
        for policy, winner in zip(cost.POLICIES, (cost.A_ID, cost.B_ID, cost.B_ID)):
            selection = cost.certified_selection(plans, cost.POLICIES[policy])
            self.assertEqual(selection["winners"], [winner])
            self.assertCountEqual(selection["pareto_frontier"], [cost.A_ID, cost.B_ID])
        with self.assertRaises(ValueError):
            cost.certified_selection(plans, (1, -1, 1, 1))

    def test_unverified_cannot_win(self):
        with patch.object(cost, "proved", return_value=False):
            result = cost.certified_selection(cost.plans(cost.Context()), (1, 1, 1, 1))
        self.assertEqual(result["result"], "NO_ASSURED_RECOVERY")
        self.assertEqual(result["cost_by_admissible_procedure"], {})

    def test_observer_and_latency_failures(self):
        for plan in cost.plans(cost.SCENARIOS["C4"]):
            decision = cost.assessment(plan)
            self.assertEqual(decision["B4"], "REJECTED")
            self.assertEqual(decision["witness"]["physical"], 1)
            self.assertEqual(decision["witness"]["credible"], 0)
        late = cost.assessment(cost.plans(cost.SCENARIOS["C6"])[1])
        self.assertGreater(late["witness"]["start"], late["witness"]["deadline"])
        self.assertEqual(late["witness"]["q"], 3)
        self.assertEqual(late["witness"]["physical"], 0)

    def test_unused_path_mutation_preserves_matching_candidate_model(self):
        a, b = cost.plans(cost.SCENARIOS["C0"])
        changed_a, changed_b = cost.plans(cost.SCENARIOS["C1"])
        self.assertNotEqual(cost.proof_profile(a).sha256, cost.proof_profile(changed_a).sha256)
        self.assertEqual(cost.proof_profile(b).sha256, cost.proof_profile(changed_b).sha256)
        self.assertNotEqual(b.context.fingerprint, changed_b.context.fingerprint)
