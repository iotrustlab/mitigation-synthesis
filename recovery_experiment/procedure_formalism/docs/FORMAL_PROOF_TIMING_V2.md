# Cold proof-archive measurements

The benchmark checks five nominal dL archives from the reference experiment and the new controlled dGL archive. Each invocation proves all the entries in one archive, including its bounded composition and witness obligations. The two water authority routes have separate archives. The controlled tank has separate archives for the automatic and manual procedures. The hydro archive consumes the checked reduction of the fixed forcing trajectory. Independent arithmetic certificate generation precedes that archive and has a separate cost. The separate game archive contains the adaptive win, its shared-power negative case, and the two fixed-choice negative cases.

## Protocol

The fixed-procedure series has ten rounds. Each executes the five archives in a pseudorandom permutation from a fixed seed. A second series runs the game archive ten times on another physical core. The two streams overlapped on the shared host. Each uses one logical CPU. The combined CSV preserves each stream’s order by grouping the fixed-procedure rounds and then the game rounds. Each invocation starts a fresh JVM and isolated prover cache, with one CPU visible to the JVM and a serial garbage collector. OS page caching and other host activity are uncontrolled. The [environment manifest](../results/paper_v2/environment_manifest.json) records the machine, toolchain and thread configuration.

The harness timestamps launch, receipt of the first archive-entry announcement, and process exit. Launch to first entry includes JVM and prover initialization and archive parsing. The tool reports a tactic duration for each entry. Adding those durations yields the archive tactic measurement. Launch to exit includes setup, tactic execution, proof export and shutdown. These nested intervals do not sum to the total. Validation of output bytes takes place after the timed process exits. Raw transcripts are transient.

Each successful repetition must reproduce every reference proof export exactly. The harness checks archive and reference-proof hashes against the [original obligation inventory](../results/milestone2/rq2_summary.json) or the [new game record](../paper_v2/game_evidence/proof_index.json). The median averages the two middle observations for an even sample count. The empirical p95 uses the nearest rank. Ten observations per archive make p95 equal to the largest observation, so it gives a descriptive upper sample value.

The prover can report restricted initialization of optional derived lemmas. The raw data identify affected invocations. Each targeted tactic still has to close and reproduce its individual proof. Timings describe these bounded models with the recorded toolchain.

## Replay

Set `KEYMAERAX_JAR` to the pinned KeYmaera X 5.1.1 release and put the specified OpenJDK and Z3 executables on the search path. The harness verifies the JAR and Z3 digests before timing. Choose two available logical CPUs on different physical cores. Set `FIXED_CPU` and `GAME_CPU` to their indices. The recorded run used 31 and 30, respectively. If recording the dependency benchmark as well, choose a third physical core for `DEPENDENCY_CPU`. From the repository root, record the shared environment before starting the measurements.

```sh
python3 -m recovery_experiment.procedure_formalism.paper_v2.scaling environment \
  --output proof-timing-run --cpu "$DEPENDENCY_CPU" --proof-cpu "$FIXED_CPU" --game-cpu "$GAME_CPU"
```

Run the series in two terminals, writing to the same new directory. In the recorded run the shorter game series began while the fixed-procedure series was active. Each command creates its own raw CSV exclusively.

```sh
python3 -m recovery_experiment.procedure_formalism.paper_v2.proof_timing \
  --series fixed --cpu "$FIXED_CPU" --output proof-timing-run
python3 -m recovery_experiment.procedure_formalism.paper_v2.proof_timing \
  --series game --cpu "$GAME_CPU" --output proof-timing-run
```

When both commands finish, combine the observations. The report checks the randomized order, counts and proof bindings before publishing the joint data.

```sh
python3 -m recovery_experiment.procedure_formalism.paper_v2.proof_timing \
  --combine proof-timing-run/proof_timing_fixed.csv proof-timing-run/proof_timing_game.csv \
  --output proof-timing-run
```

The following command regenerates the shipped JSON summary from its saved joint CSV without launching the prover. An optional `--table` destination also emits the manuscript table.

```sh
python3 -m recovery_experiment.procedure_formalism.paper_v2.proof_timing --summarize
```

The [raw observations](../results/paper_v2/formal_proof_timing_repetitions.csv) contain the run order, timing intervals, obligation counts and verification result. The [report](../results/paper_v2/formal_proof_timing_v2.json) records the archive size and fingerprints, timing definitions, quantiles and digest of the raw observations.
