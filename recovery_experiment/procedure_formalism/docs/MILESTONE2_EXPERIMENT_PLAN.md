# Cross-domain recovery experiments

The unit of analysis is a procedure queried in one bounded incident. RQ1 compares the decision at three weaker boundaries against the full contract. RQ2 checks a universal safety/service formula and a reachable successful execution on the same model. RQ3 ranks only formally admissible procedures from an identical initial state and service contract.

| Experiment | Controlled change | Measurement |
| --- | --- | --- |
| Attleboro | Remote command versus Local Hand, human readiness, power, shared hardware, delivery, flow and observer faults | Four baseline decisions, exact elapsed scans, physical flow and credible observation. A separate selector satisfiability check determines whether ranking is meaningful. |
| Controlled water | Two independent backups on a fixed tank balance with common power, pipe and observer dependencies | Two admissibility proofs, formal cost expressions and selections under three policies. P1 remains isolated. |
| Merwin HCC | Remote request, auxiliaries, synchronization, command, contact, generation chain and meter | Trace-conditioned gate and rotor arithmetic plus stage contracts and three successive generated-power observations. |
| Polish CHP | Availability and review of backup, device bootability, runtime evidence and unresolved plant readiness | Independent device, process and customer-service conclusions against pinned lifecycle bundles. |
| Scalability | Node count, number of candidates, compromised fraction and shared-resource fanout | Encoded bytes, distinct feasible valuations, generation, solver and classification times on a fixed one-tick contract. |

The [baseline reproduction](../results/milestone2_baseline_reproduction.json) pins the untouched source commit, all 234 original files, four authority/reachability regressions, the 17 Remote-study obligations and all seven original reports. Frozen records carry measured times. All aggregate reports regenerate from those records without consulting the wall clock. A fresh measurement is a new observation with its own timestamp.

## Replay

Use the repository's deterministic Python environment. Put OpenJDK 17 and Z3 4.15.4 on the executable search path, and set `KEYMAERAX_JAR` to the KeYmaera X 5.1.1 archive with SHA-256 `c72cb700992e4c9fbf052113917e039ced43fa6c512493fe5473964e18b691bb`. The checked-in inputs suffice for the new experiments. The documented upstream case paths are needed only to audit the source projections independently.

From the repository root, replay individual families into fresh scratch destinations to preserve reviewed measurements. `PROOF_OUTPUT` denotes an empty writable directory. The original jars, caches, solver paths and raw prover transcripts are local inputs.

```bash
python3 -m unittest discover -s recovery_experiment/tests -v
python3 -m recovery_experiment.procedure_formalism.verify --output-dir "$PROOF_OUTPUT/remote"
python3 -m recovery_experiment.procedure_formalism.milestone2.proofs hand --output "$PROOF_OUTPUT/hand"
python3 -m recovery_experiment.procedure_formalism.milestone2.proofs cost --output "$PROOF_OUTPUT/cost"
python3 -m recovery_experiment.procedure_formalism.milestone2.merwin_reduction --output "$PROOF_OUTPUT/hydro-reduction.json"
python3 -m recovery_experiment.procedure_formalism.milestone2.proofs merwin --output "$PROOF_OUTPUT/merwin"
python3 -m recovery_experiment.procedure_formalism.milestone2.scalability --record "$PROOF_OUTPUT/scalability.json"
python3 -m recovery_experiment.procedure_formalism.milestone2.reports --output "$PROOF_OUTPUT/results"
```

The report command validates archive bytes, proof profiles, return codes, individual proof hashes and embedded theorem entries. Its default output is the [published result directory](../results/milestone2). Fresh solver timings can vary with process startup, machine load and cache state. The [integrity manifest](../results/milestone2/milestone2_manifest.json) identifies the measurements used in the paper tables.

## Final verification

The deterministic suite ran 238 tests. All 226 enabled tests passed. The 12 CLEO-dependent parser and regression checks also passed in the dedicated historical interpreter (158.629 s). The historical Attleboro CLEO choice and sampled-flow archives discharged three additional obligations. Four original Attleboro authority and reachability entries and all 17 Milestone 1 Remote-study obligations closed in fresh runs. [Legacy regression record](../milestone2/evidence/legacy_regressions.json)

The final independent replay closed all 49 new dL obligations and reproduced every corresponding proof export byte-for-byte. It checked the hydro arithmetic certificate, reran all 192 scaling cells and reproduced the same solver answers and branch counts. The 17 result files regenerated identically. All 234 pre-existing tracked files retained their original SHA-256 digests. [Final replay record](../milestone2/evidence/final_replay.json)
