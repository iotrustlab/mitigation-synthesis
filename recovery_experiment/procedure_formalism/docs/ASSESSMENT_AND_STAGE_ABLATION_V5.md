# Evidence for the 68 assessments and their stage ablations

An assessment pairs one supplied candidate with one original operating state. The experiment retains a candidate if its bounded contract holds on all the executions of the chosen representation, with continued execution at every admitted finite prefix. The five assessment families cover two Attleboro studies, Merwin, CHP and the controlled tank. A status or threshold is a premise of the fixture. Each reported count concerns these controlled queries.

## Establishing the reference contract

The [evidence reconstruction](../paper_v5/assessments.py) reads the original scenario inputs and rebuilds the finite model. It checks the bytes and identities of the relevant dL archive and proof exports for a universal guarantee or a violation diamond. Positive results also require the nonvacuity export. Merwin uses the archived arithmetic reduction. An explicit unavailable node, excluded selector, deadline guard, omitted positive actuation in hold, or unsatisfied device or process prerequisite can instead settle a negative query. For a documentary case the reconstruction checks the backup and boot records, execution events and independently increasing scan counter in the saved evidence bundle.

Only after adjudication does the generator join the archived B1–B4 columns by study, scenario and candidate. All 68 evidence-derived decisions match B4. The independent basis is independent of the votes cast by the engineering baselines. The evidence and B4 concern the same fixture and contract. They provide no field outcome or empirical incident frequency. “Source-backed missing evidence” identifies the specific stored scenario or evidence bundle that leaves a field unresolved. An unknown integrity premise in a research scenario does not describe the condition of an installed device.

| Primary basis | Assessments | Supported conclusion |
| --- | ---: | --- |
| Universal proof and reachable execution | 11 | Safe, timely, observed service under the named premises. |
| Known false prerequisite | 31 | The requested candidate lacks a required input, enabled stage or positive-service action. |
| Reachable formal counterexample | 20 | An allowed execution refutes the universal contract. |
| Documented missing evidence | 4 | Two unresolved dependency relations admit both outcomes. Two CHP questions lack customer-supply or persistence evidence. |
| Missing physical model | 2 | Normal device execution and process-readiness queries lack the physical CHP model needed for composition. |

Some positive rows share the same checked archive under equivalent model inputs. There are 11 supported assessment rows. Five CHP queries also have a trace-backed device witness. Four are unresolved and one has an explicitly false process prerequisite. A device-level observation is additional evidence, so the five do not increase the denominator. The [JSON](../results/paper_v5/assessment_evidence_basis.json) and [CSV](../results/paper_v5/assessment_evidence_basis.csv) give one adjudication, source selector and boundary per assessment. Source selectors following a hash sign identify the original declaration or JSON object within a package-relative path.

## Rerunning stage relations

The [ablation generator](../paper_v5/ablation.py) operates on the guarded assignments consumed by the original proof generator. The finite interpreter checks every reachable alternative using exact rational arithmetic. An empty successor set, a missed deadline, a safety violation or one failed required endpoint precludes retention. Each variant can weaken only its declared boundary. The resulting weakened-contract verdict is compared with the separately established full-contract evidence. Retaining an assessment under an ablation supplies no new service proof.

| Variant | Measured substitution and applicability |
| --- | --- |
| FULL | Apply the original contract to each of the 68 assessments. Passive hold has no positive-service action. CHP has no bound physical model and corresponding measurements. |
| NO_AUTHORITY | Treat the initiating actor as present and authorized. In water, set actor readiness to the request origin, retaining the three mandatory scan durations. Preserve mode and interlock conditions, communication, equipment start times and every subsequent stage. The 57 modeled candidates have an actor relation. CHP has no corresponding timed actor model, and passive hold has no actor. |
| COLLAPSE_DELIVERY | Replace the independently modeled delivered bit with controller output in Remote, breaker contact with permitted close demand in hydro, or actuation with command output in the tank. Power, relay protection, plant and observation requirements still apply. Hand already has a direct local copy. The 40 applicable rows exclude Hand, hold and CHP. |
| COLLAPSE_PLANT | Treat a running pump or generator, or a powered tank drive, as delivering the requested threshold. The water surrogate gives 5 L/s and its associated pressure, and the generation surrogate gives 1 MW at each required poll. The original timing, safety accumulator and meter's trust/freshness tests remain in place. In the weakened model the meter samples the substituted quantity. This removes independent physical correspondence. A fresh reading of the proxy can differ from the original physical meter reading. The tank retains its actual balance for safety. In seven CHP end-to-end/process queries the confirmed heartbeat serves as both device proxy and observation. Separate physical safety is unbound, while an explicitly false process prerequisite still prevents retention. The two CHP queries specifically about external supply and cyber persistence and the two passive holds have no such proxy for their requested property. |
| NO_OBSERVATION | Drop the observer transitions and terminal evidence conjuncts, retaining actual physical service, safety and time. This comparison requires a bound physical contract. It applies to the same 57 modeled candidates as the actor ablation. |
| BREAK_SHARED_IDENTITY | Change the status lookup from resource identity to (candidate, resource). Copy each declared status to its candidate-local node. The fixed-state comparison requires two actually assessed candidates sharing a dependency in the same state. Eight Attleboro assessments and 16 controlled-tank assessments meet that condition. |

| Variant | Applicable | Retained | Independently proved | Known failure | Unresolved |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full contract | 68 | 11 | 11 | 0 | 0 |
| Assume actor | 57 | 17 | 11 | 6 | 0 |
| Copy command | 40 | 14 | 10 | 2 | 2 |
| Use actuator proxy | 64 | 16 | 11 | 3 | 2 |
| Omit observation | 57 | 18 | 11 | 7 | 0 |
| Clone shared identities at fixed statuses | 24 | 7 | 7 | 0 | 0 |

The actor substitution admits absent and late Hand starts. Copying the delivered command admits M5 and MER6, which have a known failed guarantee, and M13 and MER10, which have unresolved integrity. A running actuator masks blocked water flow in M7/H7 and missing electrical coupling in MER7. A heartbeat masks the absent process evidence in CHP0/CHP5. Dropping the observer admits seven cases with stale or untrusted readings, including two controlled C4 candidates sharing one meter. Categories and applicability can overlap across variants. Their counts must not be added.

Cloning identities while retaining known statuses changes no individual verdict. The [placement diagnostic](../results/paper_v5/stage_ablation.json) separately uses each recorded single shared-resource mutation and places its status on just one candidate-local copy at a time. In C3 both original paths depend on a single unavailable feed. Under the alternative representation, allocating the outage to either one of the two cloned feeds leaves the other candidate eligible. No single fixed candidate survives every placement. The shared meter in C4 and shared pipe in C7 have the same pattern. In M6 the mutually exclusive selector still excludes Hand even if its VFD copy is healthy. This diagnostic concerns coupling of candidate sets and does not change a stipulated shared outage in the full model.

The [row-level results](../results/paper_v5/stage_ablation.json) retain each eligibility decision, including inapplicability. The [aggregate CSV](../results/paper_v5/stage_ablation.csv) and [domain CSV](../results/paper_v5/stage_ablation_by_domain.csv) include the identities of all unsupported retentions. The manuscript figure is generated from the same totals.

Run these commands from the implementation repository. The optional figure path selects an adjacent manuscript checkout.

```sh
python3 -m recovery_experiment.procedure_formalism.paper_v5.ablation --figure ../redundancy-analysis-paper-dsn-27/figures/stage-ablation-v5.tex
python3 -m unittest recovery_experiment.tests.test_paper_v5_ablation
```
