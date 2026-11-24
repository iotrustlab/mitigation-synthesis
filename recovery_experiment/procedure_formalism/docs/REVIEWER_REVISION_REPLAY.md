# Replaying the reviewer revision

The baseline revision is `fa719386e782766f01a8db770d7b128ccba3ad99`. Its 359 tracked files were inventoried before this revision. The new reports live in [the reviewer result directory](../results/paper_v2). All commands below start at the implementation repository root.

## Reproduce the results used by the manuscript

```sh
python3 -m recovery_experiment.procedure_formalism.paper_v2.reproduce
python3 -m unittest discover -s recovery_experiment/tests
```

The first command checks the original and new proof exports and their identities, computes baseline counts from individual assessments, recomputes the exact policy experiments, and calculates the timing statistics from captured measurements. It compares each regenerated report with its published counterpart in a temporary directory. An optional `--output` retains that directory. The clock observations, order of the measured runs and machine manifest are the inputs to this deterministic step. Fresh timing observations will generally differ.

## Run fresh proofs and timings

Use the pinned KeYmaera X 5.1.1 jar identified by `KEYMAERAX_JAR`, with OpenJDK 17 and the pinned Z3 4.15.4 executable available on the command search path. Choose fresh output directories. The Linux benchmark uses CPU affinity, GNU time and one solver worker. The recorded hardware and tool fingerprints appear in the [environment manifest](../results/paper_v2/environment_manifest.json).

```sh
python3 -m recovery_experiment.procedure_formalism.paper_v2.formal --output replay-v2/fixed
python3 -m recovery_experiment.procedure_formalism.paper_v2.game prove --output replay-v2/game --result replay-v2/adaptive_game.json
python3 -m recovery_experiment.procedure_formalism.paper_v2.scaling measure --output replay-v2/dependency
```

The [proof-timing protocol](FORMAL_PROOF_TIMING_V2.md) gives commands and measurement boundaries for fresh JVMs, cached files and proof export comparisons. The [formal design](PAPER_FORMAL_SEMANTICS_V2.md), [canonical case records](CANONICAL_SEMANTIC_CASES.md) and [initial reviewer audit](STRONG_REVIEWER_RESULTS_AUDIT.md) state which results support each claim. The historical proof and CLEO environments retain their original procedures in the [cross-domain experiment plan](MILESTONE2_EXPERIMENT_PLAN.md).

## Interpreting the comparisons

B1–B3 are partial analyses evaluated against an end-to-end contract. A declined or out-of-scope decision differs from a witnessed service failure. The [contingency CSV](../results/paper_v2/baseline_contingency.csv) records every baseline decision group crossed with every B4 result. The [cost sensitivity report](../results/paper_v2/cost_sensitivity.json) records the exact perturbations and ties for the two jointly proved candidates. The [dependency benchmark](../results/paper_v2/dependency_scalability_v2.json) and [proof archive timing](../results/paper_v2/formal_proof_timing_v2.json) measure different operations. The [adaptive game](../results/paper_v2/adaptive_game.json) assumes an observed resource state followed by one recovery decision. A single shared-feed failure can remove both available routes.

## Regression check

The default suite discovered 250 tests. It passed 238 and skipped 12 legacy CLEO checks. All 12 passed in the dedicated historical interpreter with its documented CPU configuration. An exploratory single-CPU replay had left one historical ODE subgoal open; restoring the original execution configuration resolved it without changing the formula or tactic. Three historical CLEO Attleboro obligations and four authority/reachability obligations also replayed. The 17 Remote and 49 later cross-domain dL proof exports matched the frozen files byte for byte. A fresh hydro arithmetic check returned unsatisfiable for the negated certificate, with only its timestamp and wall time differing. All 359 original tracked files retained their digests.
