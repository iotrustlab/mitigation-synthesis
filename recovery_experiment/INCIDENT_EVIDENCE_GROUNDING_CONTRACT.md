# Incident Evidence And Grounding Contract

## Scope

This deterministic front end converts synthetic telemetry, alerts, and command
history into the existing formal recovery input. It does not add a template or
attack class, prove a theorem, issue a control command, or claim an industrial
deployment.

There is no LLM. `IncidentInterpreter` is only an interface and
`DeterministicIncidentInterpreter` is the sole reference implementation. A
future LLM implementation must return the same provenance-aware
`CandidateRecoveryContext` and pass through `ground_candidate_context`; it
cannot send raw evidence or ungrounded claims to the formal engine.

## Evidence, Candidate, And Trust

`incident_evidence.py` provides JSON-serializable monitoring structures:

| Structure | Raw meaning | Not a formal conclusion |
| --- | --- | --- |
| `Observation` | timestamped state, command, or timing reading | a tank reading does not establish trusted control |
| `Alert` | IDS or anomaly indication | an alert alone does not establish attacker authority |
| `CommandEvent` | command history and authorization status | a command value alone does not establish compromise |
| `ResourceObservation` | available, unavailable, or unknown status | availability does not establish independent trust |
| `IncidentEvidence` | incident window and records | metadata is checked during grounding |

`candidate_context.py` holds the pre-trust interpretation. Each important
`CandidateClaim` records its value, status, evidence IDs, sources, rule IDs,
confidence when available, and note. A candidate may say P2 appears
operational, but cannot claim P2 is an independent backup.

`trusted_plant_knowledge.py` is manually maintained configuration, not
telemetry. It declares `T1 -> {P1, P2} -> T2`, P1's `P1_command_path`, P2's
backup relationship, the isolator, the two hold gates, the attacker alphabet,
and trusted observation sources. `RecoveryConfiguration` independently fixes
timing, trusted and controllable controls, assurance budget, and service needs.

```text
P2 observation = AVAILABLE       observed operational status
P2_command in trusted_controls   configured trust for this incident
P2_command controllable          configured recovery authority
P2 valid for P1                  static topology/backup relationship
```

All relevant facts are required before P2 takeover is available. A missing,
unavailable, or untrusted P2 is never silently promoted. A known untrusted P2
can still permit evaluation of the separate safe-hold template.

## Interpretation And Grounding

`incident_interpreter.py` records the complete deterministic rules in
`INTERPRETATION_RULES`:

1. A strictly latest non-invalid observation wins; a latest tie remains a
   conflict instead of using an arbitrary tie break.
2. P1 compromise requires both a relevant P1 alert and an unauthorized P1
   command event; command value alone is insufficient.
3. That pair maps only to `modify_primary_pump_command`.
4. Resource status follows the same latest/tie-conflict rule.
5. Only unauthorized P1 `ON` and `OFF` events form a formal attacker schedule;
   unsupported commands are rejected, never approximated.
6. Timing comes from observations. Explicit configuration may ground a missing
   candidate timing, but no default is invented and conflicts are not rounded.

`context_grounding.py` takes a candidate, `TrustedPlantKnowledge`, and
`RecoveryConfiguration`. Success produces `GroundedRecoveryContext`: the
unchanged downstream `RecoveryContext`, field provenance, resource records,
and any representable attacker schedule. Formal modules consume only that
established `RecoveryContext`.

| Status | Meaning |
| --- | --- |
| `GROUNDED_CONTEXT` | the fixed topology, evidence, and configuration support formal assessment |
| `INSUFFICIENT_EVIDENCE` | a required non-resource claim is absent |
| `CONFLICTING_EVIDENCE` | latest equally ranked evidence disagrees |
| `UNSUPPORTED_COMPONENT` | the component is outside the modeled P1 control surface |
| `UNSUPPORTED_ATTACK_CAPABILITY` | no formal attacker-alphabet mapping exists |
| `UNKNOWN_RESOURCE_STATUS` | resource health is absent or explicitly unknown |
| `UNTRUSTED_RESOURCE` | reserved for strict resource-trust rejection; known untrusted resources currently remain grounded but unavailable so hold may be assessed |
| `MISSING_TIMING_INFORMATION` | neither evidence nor explicit configuration supplies required timing |
| `INCOMPATIBLE_PLANT_KNOWLEDGE` | static topology, timing, or mapping disagrees with the model |
| `INVALID_EVIDENCE` | malformed or untrusted-source data cannot be used |

Failure stops formal construction, certificate checks, selection, simulation,
and cost estimation. The pipeline fails closed rather than making a best-effort
recovery recommendation.

## Offline Pipeline

`incident_pipeline.py` implements this no-online-proof flow:

```text
IncidentEvidence
  -> DeterministicIncidentInterpreter
  -> CandidateRecoveryContext
  -> ground_candidate_context
  -> existing RecoveryContext
  -> assess_template_formal_problems
  -> existing reviewed certificate checks and select_recovery_policy
```

`run_incident_pipeline` records every stage and reports
`online_prover_invoked=False`. It never calls CLEO; it only consults existing
reviewed certificate checkers. A generated model without reviewed provenance
remains unverified and unauthorized.

### Worked Example

`A-immediate-nominal-1` supplies `x1=7`, `x2=6`, P1 command `OFF`, a P1
unauthorized-command alert, an unauthorized P1 `OFF` event, and operational
reports for P2, the isolator, and both hold gates.

1. Interpretation selects latest tank values and derives P1 compromise plus
   `modify_primary_pump_command` from the alert and command history.
2. Grounding confirms the P2/P1 backup relation and authority for P2,
   isolation, and gates, then creates the existing `RecoveryContext`.
3. Existing resource assessment finds flowing P2 takeover and safe hold.
4. Existing construction and reviewed certificate checkers bind each template
   to its own formal artifact.
5. The continuous positive-service request rejects safe hold as
   service-inadequate and selects `flowing_backup_takeover`.

This is synthetic certificate/selection output, not a physical command or live
SWaT capability.

## Gold Dataset And Evaluation

`incident_dataset.py` provides a fixed-seed (`20260924`) 27-case suite. It has
raw evidence, separately constructed candidate/context labels, and declarative
scenario-spec gold labels. It does not import or call the interpreter or
grounder to generate labels. Cases cover immediate and reviewed delayed
schedules, P2 unavailable or untrusted, missing authority,
certificate-boundary state, continuous-service limits, unsupported timing,
conflicts, and missing evidence.

`incident_evidence_evaluation.py` measures field accuracy, grounding
accept/reject errors, template/formal-model/certificate/service/decision
accuracy, and first divergence. Categories include interpretation, grounding,
template selection, formal-model selection, certificate selection, service
admissibility, and cost selection. A future LLM should be measured on both
extraction and downstream recovery consequences.

```bash
python3 -m unittest recovery_experiment.tests.test_incident_evidence_pipeline -v
python3 - <<'PY'
from recovery_experiment.incident_evidence_evaluation import evaluate_deterministic_pipeline
print(evaluate_deterministic_pipeline().as_dict())
PY
```

These commands use standard-library code and existing reviewed artifacts. They
do not deploy, reconfigure, reset, execute attacks, or invoke an online prover.
