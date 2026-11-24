import json
import unittest
from dataclasses import replace

from recovery_experiment.procedure_formalism.attleboro import HAND_ID, REMOTE_ID, attleboro
from recovery_experiment.procedure_formalism.procedure import (
    DependencyKind, DependencyStatus, EvidenceStatus, ProcedureEvent, field_evidence,
)


class ProcedureSchemaTests(unittest.TestCase):
    def setUp(self):
        self.candidates = attleboro()
        self.remote = self.candidates["remote"]
        self.hand = self.candidates["hand"]
        self.vfd = self.remote.required_dependencies["vfd"]

    def test_shared_downstream_identity_and_command_boundaries(self):
        shared = {"vfd", "pump", "motor_power", "trip_path", "water_path", "observer"}
        self.assertEqual(shared, set(self.remote.shared_dependencies))
        self.assertEqual(shared, self.remote.required_dependencies.keys() & self.hand.required_dependencies.keys())
        for node_id in shared:
            node = self.remote.required_dependencies[node_id]
            self.assertIs(node, self.hand.required_dependencies[node_id])
            self.assertEqual(node.required_by, (REMOTE_ID, HAND_ID))
        self.assertNotIn("plc", self.hand.required_dependencies)
        self.assertNotIn("hand_panel", self.remote.required_dependencies)
        self.assertIsNone(self.hand.communication_path)

    def test_mutation_changes_one_common_snapshot(self):
        for key in self.remote.shared_dependencies:
            candidates = attleboro({key: DependencyStatus.UNAVAILABLE})
            remote_node = candidates["remote"].required_dependencies[key]
            hand_node = candidates["hand"].required_dependencies[key]
            self.assertIs(remote_node, hand_node)
            self.assertIs(remote_node.status, DependencyStatus.UNAVAILABLE)
            self.assertIs(self.remote.required_dependencies[key].status, DependencyStatus.TRUSTED)

    def test_status_and_evidence_are_independent(self):
        self.assertIs(self.vfd.status, DependencyStatus.TRUSTED)
        self.assertIs(self.vfd.source_status, EvidenceStatus.RESEARCH_AUTHORED)
        self.assertIs(self.vfd.kind, DependencyKind.ACTUATOR)
        unattested = replace(self.vfd, source_status=EvidenceStatus.UNKNOWN)
        self.assertIs(unattested.status, DependencyStatus.TRUSTED)
        for incorrect in ("TRUSTED", "BROKEN", EvidenceStatus.UNKNOWN):
            with self.assertRaises(ValueError):
                replace(self.vfd, status=incorrect)
        with self.assertRaises(ValueError):
            replace(self.vfd, source_status=DependencyStatus.UNKNOWN)
        with self.assertRaises(ValueError):
            replace(self.vfd, kind="HARDWARE")

    def test_procedure_validates_resource_bindings_and_horizon(self):
        for changes in (
            {"actor": "missing"}, {"shared_dependencies": ("plc",)},
            {"required_dependencies": {"wrong_name": self.vfd}}, {"actor_ready_time": -1},
            {"deadline": 4}, {"attacker_effects": {"missing": "Boolean output"}},
            {"source_references": ()}, {"evidence_status_by_field": {"actor": EvidenceStatus.SOURCE_BACKED}},
            {"evidence_status_by_field": field_evidence(actor=DependencyStatus.TRUSTED)},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.remote, **changes)

    def test_local_readiness_and_common_context(self):
        state = {"remote_selected": 0, "hand_selected": 1}
        candidates = attleboro(initial_state=state, local_ready_time=4)
        self.assertGreater(candidates["hand"].actor_ready_time, candidates["hand"].deadline)
        self.assertEqual(candidates["hand"].initial_state, candidates["remote"].initial_state)
        self.assertEqual(candidates["hand"].initial_state["hand_selected"], 1)
        self.assertEqual(candidates["remote"].initial_state["remote_selected"], 0)
        self.assertEqual(self.remote.initial_state["remote_selected"], 1)
        self.assertNotIn("hand_panel", candidates["hold"].required_dependencies)
        self.assertIsNone(candidates["hold"].plant_model)

    def test_initial_state_validates_and_copies_inputs(self):
        state = {"flow_blocked": 1}
        candidates = attleboro(initial_state=state)
        state["flow_blocked"] = 0
        self.assertEqual(candidates["remote"].initial_state["flow_blocked"], 1)
        for invalid in ({"trip": 2}, {"typo": 0}, {"initial_flow": -1}, {"ph_out_of_range": 1, "trip": 0}):
            with self.assertRaises(ValueError):
                attleboro(initial_state=invalid)
        self.assertEqual(attleboro(initial_state={"ph_out_of_range": 1})["remote"].initial_state["trip"], 1)
        with self.assertRaises(ValueError):
            attleboro({"unknown_resource": DependencyStatus.TRUSTED})

    def test_independent_event_labels_and_portable_representation(self):
        self.assertEqual(len(ProcedureEvent), 8)
        evidence = {ProcedureEvent.CONTROLLER_OUTPUT_SET: True, ProcedureEvent.ACTUATION_DELIVERED: False}
        self.assertNotIn(ProcedureEvent.SERVICE_ESTABLISHED, evidence)
        payload = json.loads(json.dumps(self.remote.as_dict(), allow_nan=False))
        self.assertEqual(payload["procedure_id"], REMOTE_ID)
        self.assertEqual(payload["required_dependencies"]["vfd"]["status"], "TRUSTED")
        self.assertEqual(payload["evidence_status_by_field"]["plant_model"], "RESEARCH_AUTHORED")
        payload["initial_state"]["trip"] = 1
        self.assertEqual(self.remote.initial_state["trip"], 0)
