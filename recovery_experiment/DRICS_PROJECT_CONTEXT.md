# Dr.ICS Project Context

## Purpose and assurance boundary

Dr.ICS is a research prototype for incident-specific, formally assured recovery
in industrial cyber-physical systems. Its implemented pipeline converts
synthetic incident evidence into a provenance-bearing candidate context, grounds
that context against trusted plant knowledge, constructs one of the supported
formal recovery problems, checks coverage by reviewed offline certificates, and
selects only among formally and operationally admissible policies.

The interpreter does **not** establish plant truth or authorize control. Trusted
grounding, formal construction, certificate coverage, service checks, and policy
selection remain separate stages. The code does not invoke CLEO online and does
not issue actuator commands.

## Implemented synthetic plant

The current plant is a synthetic two-tank parallel-path system:

```text
T1 -> {P1, P2} -> T2
x1' = qin - q1 - q2
x2' = q1 + q2 - qout
```

P1 is the compromised primary path. P2 is a possible trusted backup. A trusted
physical isolator can remove P1's influence. Physical existence, operational
availability, trust, and recovery authority are represented separately. External
demand, physical withdrawal, and delivered service are also separate concepts.
This is not a SWaT or SPHERE deployment.

## Recovery templates and timing

Exactly two resource-aware template families are implemented:

1. **Flowing backup takeover** requires trusted isolation and a trusted,
   controllable P2. It can preserve delivery while P2 starts when the initial
   tank state has the required margins.
2. **Controlled safe hold** requires trusted isolation plus trusted inflow and
   downstream-service controls, but not P2. It establishes finite-horizon safety
   with `qin = qout = qdelivered = 0`; it does not establish positive service.

The typed builder in `recovery_model_builder.py` targets only this plant family.
It represents requested/pending/effective isolation, pending/available backup,
and attacker-commandable versus physically effective control. Bounded schedules
use `IsolationDelay = n*T` and `StartupDelay = m*T`, require integral ratios,
`n >= 0`, and `m > n`; unsupported schedules are rejected rather than rounded.
Delayed-isolation games give the attacker a fresh binary P1 choice before each
modeled pre-isolation interval.

## Formal models, proofs, and certificates

The repository contains distinct immediate, timed, parameterized,
state-dependent, delayed-isolation, intermediate-delay, bounded-delay, and
controlled-safe-hold renderers, proof profiles, verifiers, and reviewed proof
records where applicable. CLEO parses the generated differential-game-logic
envelope, sends arithmetic obligations to Z3, and sends hybrid-system
obligations to its bundled KeYmaera X backend.

A CLEO `VERIFIED` result is offline proof evidence, not runtime authorization.
The lifecycle distinguishes formal-problem construction, theorem verification,
artifact review, certificate issuance, and runtime context coverage. Manifests
bind the relevant renderer, envelope/model, proof profile, verifier, policy and
model identities, assumptions, and timing semantics. A newly verified generated
schedule remains unauthorized until its artifacts and provenance are reviewed.

## Resource, service, and cost logic

Template applicability depends on explicit trusted-resource flags. If neither
implemented template applies, the result means no supported template—not that
recovery is globally impossible. Safety is a hard requirement. Service
admissibility is explicit and may reject a certificate-covered safe hold when
positive service is required.

Costs are derived from simulated traces and combine delivery shortfall, recovery
duration, intervention cost, and backup use. The current implementation has no
formal cost bound and proves no global cost optimality; cost only ranks already
admissible candidates.

## Evidence, deterministic interpretation, and grounding

`incident_evidence.py` defines deterministic JSON representations for
observations, alerts, command events, resource observations, and complete
incident evidence. `incident_interpreter.py` maps evidence to the existing
`CandidateRecoveryContext` schema. Candidate claims retain value, evidence IDs,
source, rule, status, and confidence. In the baseline interpreter, a P1
compromise requires both a relevant alert and unauthorized command evidence.

`trusted_plant_knowledge.py` separately holds topology, component roles, trusted
control mappings, supported attacker actions, bounds, timing configuration, and
recovery authority. `context_grounding.py` validates candidates against that
knowledge and either produces the formal-facing `RecoveryContext` with
provenance or fails closed with a structured reason. Missing or conflicting
values are not silently filled.

## Dataset and current evaluation path

`incident_dataset.py` builds the fixed-seed synthetic gold dataset. It covers
healthy and unavailable/untrusted resources, missing or conflicting evidence,
unsupported timing, certificate-margin failures, and service requirements.
Gold expectations extend through grounding, template and formal-model identity,
certificate behavior, service outcome, and final decision. The canonical
evaluation entry point is:

```bash
python -m recovery_experiment.incident_evidence_evaluation
```

The deterministic interpreter is the retained baseline/oracle-style comparison;
its results must be measured from the current code rather than hardcoded from a
historical report.

## Current limitations

- Synthetic two-tank, parallel-pump plant and synthetic evidence only.
- Binary P1 attacker choices and simplified constant flows.
- Finite recovery horizon and fixed-policy verification, not arbitrary strategy
  synthesis.
- Manually supplied trusted configuration and assumed trusted physical isolator.
- No sensor-uncertainty model, live telemetry, real-world trust attestation, or
  deployment assurance.
- No formal cost-optimality theorem.
- No live Qwen smoke test or 27-case LLM baseline has been run; the current
  GT 1030 is unsuitable, so real inference requires an allocated CHPC GPU.

## LLM interpreter boundary

`LLMIncidentInterpreter` implements the same interpreter interface and emits
exactly the existing `CandidateRecoveryContext` through a model-independent,
OpenAI-compatible backend. Qwen 3.5-9B is the initial development model, not an
assumption in downstream code. Model output feeds the same grounding and formal
pipeline. It must not invent trusted plant facts, bypass grounding, choose or
issue certificates directly, claim safety, generate runtime envelopes, or
authorize/issue actuator actions. Evaluation tracks errors through
interpretation, grounding, template choice, formal-model identity, certificate
choice, service admissibility, cost selection, and final decision. See
`LLM_INCIDENT_INTERPRETER.md` for the pinned artifact and GPU workflow.

## Do not redo or broaden without an explicit research task

- Do not replace the deterministic interpreter when adding an LLM comparison.
- Do not change formal assumptions, reviewed manifests, or certificates merely
  to satisfy environment or test failures.
- Do not add plant topologies, recovery templates, attack capabilities, or
  recovery scenarios as infrastructure work.
- Do not describe the synthetic system as a deployed testbed.
- Do not treat CLEO verification alone as runtime recovery authorization.

For detailed contracts, see `README.md`, `RECOVERY_MODEL_BUILDER_DESIGN.md`,
`INCIDENT_EVIDENCE_GROUNDING_CONTRACT.md`, `BOUNDED_SCHEDULE_CONTRACT.md`, and
`RESOURCE_AWARE_RECOVERY_CONTRACT.md` in this directory.
