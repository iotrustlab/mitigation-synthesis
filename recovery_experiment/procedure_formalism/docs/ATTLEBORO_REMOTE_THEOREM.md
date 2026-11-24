# Attleboro Remote bounded recovery theorem

The object of the proof is the historical source-derived research fixture. The operator is ready and authorized at tick 0. A rising Start arrives after PLC eligibility, in exclusive Remote mode on utility with generator off, reset cleared, no protection trip and normal pH. The controller is powered. The pump is initially stopped, with zero forward flow. Motor power, panel, drive and pump remain available, the water path is clear, and the observer returns fresh values. The fixture assumes eligibility and power remain stable for three 100 ms scans. A separate three-scan PLC contract proves the command persists after the first-scan Start pulse is released. It starts with no pending/sealed demand, zero wait count and a low previous request, applies the 50-scan timeout, and permits either confirmation or loss of confirmation on the final controller scan. A trusted delivery stage copies the command. The modeled Boolean disturbances are persistent choices over this short window. The theorem does not establish an ST refinement or interprocess scheduling bound.

Let Γ bind these inputs and the initial state, and let α be the generated sequence on this closed snapshot. The Remote theorem is

```
Γ → [α] (safe = 1 ∧ t = 3 ∧ run = 1 ∧ physical = 1 ∧ established = 1
         ∧ q ≥ 5 ∧ pressure ≤ 90 ∧ trusted = 1 ∧ fresh = 1
         ∧ observed = q ∧ observedPressure = pressure)
```

`q` and `observed` are physical and observed flow (L/s), `pressure` and `observedPressure` are in psi, and `t` counts elapsed 100 ms scans. The `safe` accumulator checks the initial and every post-scan sample for flow in [0,10], pressure in [30,90], no trip and normal pH. Physical service requires flow ≥5, pressure ≤90, normal pH and no trip. Credible establishment requires a trusted, fresh observer whose two readings match the plant, satisfy those service bounds and coincide with physical service. This is a snapshot observation at the procedure deadline. The observer is a research assumption distinct from the plant itself.

For scan i, effective demand requires exclusive Remote selection, a drive request, motor power and no trip. A drive starting from rest confirms run on its second consecutive powered scan. Set target Q to 10 L/s iff running and unblocked and otherwise to zero. Advance `u = q + (2/5)(Q−q)`, set `q = 0` if `u < 1/100` and otherwise `q = u`, then set `pressure = 30 + 3q`. Each of three mandatory scans increments `t` once. For the stated initial state the three flow samples are 0, 4 and 32/5. Pressure never exceeds 246/5 psi. These are sampled safety and service claims. Between-scan hydraulics are outside the model.

The proof obligations cover request delivery, PLC acceptance/output, delivered actuation, consecutive drive response and plant safety/service, and trustworthy observation. A separate universal formula executes their sequential composition. A diamond establishes reachability of observation and service at exactly three ticks. An independent witness establishes satisfiability of Γ. The controller-to-delivery boundary admits a Boolean disturbance independently of the PLC's output in the corresponding mutation. A proved existential violation for a declared disturbance is evidence about this fixture.

The historical design supplies mode and authority conditions, reset after power restoration, hardwired trips, and forward-flow metering. The rising-edge implementation, scan period, command timing, two-scan delay, flow update, pressure relation, safety and service bounds, observer and disturbance alphabets are research-authored. Bundle evidence corroborates selected traces. The generated proof records identify the formulas formally established. Actual staffing, wiring, transport delays, site hydraulics, limits, instrument health and customer service remain unknown.

The controller and simulator correspondence is pinned in [the source map](../../attleboro/source_to_model_map.md). The new archive has a distinct identity from both [the historical authority proof](../../attleboro/remote_authority.kyx) and [the one-step flow envelope](../../procedure_study/cleo/attleboro_sampled_flow.envelope).

The generated single-assignment program samples each fresh stage slot and then tests the conjunction of their guarded defining relations. Each definition uses only earlier slots. This is the relational form of sequential execution. The execution witness uses the same program as the universal theorem. The five stage results use successive prefixes, so each includes the assumptions and transitions up to its boundary. The composed proof checks the full sequence directly.

## Replay

From the repository root, with Java and Z3 on the executable search path and the downloaded JAR identified by `KEYMAERAX_JAR`, run

```sh
python3 -m recovery_experiment.procedure_formalism.verify --output-dir proof-replay
python3 -m unittest recovery_experiment.tests.test_procedure_formal
```

The replay creates the archives, proof files and per-obligation index in the chosen output directory. It creates an isolated KeYmaera X user home and uses fresh, relative input and output names. Original proof files can therefore be shared without editing their provenance comments. The checked run used OpenJDK 17.0.21.1, the KeYmaera X 5.1.1 release JAR (SHA-256 `c72cb700992e4c9fbf052113917e039ced43fa6c512493fe5473964e18b691bb`) and the Z3 4.15.4 binary distributed with `z3-solver==4.15.4.0`. The prover reported restricted initialization of optional derived lemmas. Every required archive entry separately produced a `PROVED` result and a proof file. The obligation timings exclude JVM startup and the per-archive wall times include it. [KeYmaera X release](https://github.com/LS-Lab/KeYmaeraX-release/releases/tag/5.1.1) · [Recorded obligations](../proof_records/verification.json)

The mutation archives use the same transition semantics with an existential postcondition that violates the full Remote contract. The M13 diamond establishes a possible violation in the union of nominal and adverse models. Its operational classification remains UNKNOWN until the delivery state is resolved. The saved [positive archive](../models/M0.kyx) contains the five prefixes, their composition, the held-output controller contract and the two satisfiability/reachability witnesses.
