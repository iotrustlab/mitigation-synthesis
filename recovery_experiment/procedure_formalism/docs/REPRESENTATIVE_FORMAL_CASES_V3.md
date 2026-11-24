# Representative formal cases

The [case matrix](../results/paper_v3/representative_case_matrix.json) records ten fixture assessments in six groups. The decision concerns the evidence for the stipulated incident. The O1–O8 columns concern the bound model. In particular, M13 and MER10 admit both a successful and an adverse execution while leaving the actual incident unresolved.

| Case | Assessment | O1 | O2 | O3 | O4 | O5 | O6 | O7 | O8 | Incident |
|---|---|---|---|---|---|---|---|---|---|---|
| S1 | M0 | PROVED | PROVED | PROVED | PROVED | PROVED | PROVED | PROVED | INAPPLICABLE | PROVED |
| S2 | M5 | PROVED | PROVED | PROVED | PROVED | REFUTED | REFUTED | REFUTED | INAPPLICABLE | REJECTED |
| S3 | M13 | PROVED | PROVED | PROVED | PROVED | REFUTED | REFUTED | REFUTED | INAPPLICABLE | UNKNOWN |
| S4 | H0 | PROVED | PROVED | PROVED | PROVED | PROVED | PROVED | PROVED | INAPPLICABLE | PROVED |
| S4 | H1 | PROVED | REFUTED | REFUTED | INAPPLICABLE | INAPPLICABLE | INAPPLICABLE | INAPPLICABLE | INAPPLICABLE | REJECTED |
| S4 | H2 | PROVED | PROVED | REFUTED | PROVED | PROVED | PROVED | REFUTED | INAPPLICABLE | REJECTED |
| S5 | MER0 | PROVED | PROVED | PROVED | PROVED | PROVED | PROVED | PROVED | INAPPLICABLE | PROVED |
| S5 | MER6 | PROVED | PROVED | PROVED | PROVED | REFUTED | REFUTED | REFUTED | INAPPLICABLE | REJECTED |
| S5 | MER10 | PROVED | PROVED | PROVED | PROVED | REFUTED | REFUTED | REFUTED | INAPPLICABLE | UNKNOWN |
| S6 | CHP0 | UNBOUND_MODEL | UNBOUND_MODEL | UNBOUND_MODEL | UNBOUND_MODEL | UNBOUND_MODEL | UNBOUND_EVIDENCE | UNBOUND_MODEL | INAPPLICABLE | UNKNOWN |

## How to read the obligations

O1 has a concrete valuation for the encoded premises. O2 checks that the fixed procedure can execute. O3 combines continuation at every admitted semantic prefix with arrival at the required boundary or persistent failure. O4 checks sampled safety. O5 checks the terminal physical service predicate on executions without an explicit persistent failure. O6 checks both production of credible evidence and its correspondence to the physical measurement. O7 checks the original, deadline-bearing composition. O8 applies to the separate cost fixtures.

For nominal M0, H0 and MER0, O4, O5 and O7 refer to conjuncts of the same composed proof. O6 also has a checked full-program projection that explicitly asserts evidence production. O3 joins a checked boundary box to the complete finite-prefix audit. For enabled mutations, each component marked PROVED by finite model checking was evaluated on every reachable exact rational terminal state. Each failed universal goal has an admitted counterexample. The JSON distinguishes dL proof records, finite checks, and trace evidence. Model hashes digest the complete archive. Proof hashes digest the individual theorem records.

## S1 · Attleboro water

**M0 · PROVED.** The composed box covers the three required scans, sampled safety, service at the deadline and a corresponding meter reading. [Checked theorem](../proof_records/M0/end_to_end.kyp).

## S2 · Attleboro water

**M5 · REJECTED.** The stipulated compromised delivery admits a reachable suppressed command under which physical flow and its fresh reading are zero. [Checked theorem](../paper_v2/formal_evidence/proof_records/v2_M5/specific_witness.kyp).

On the zero-output path, the trustworthy observer reports zero. The evidence implication holds, but the required positive evidence is absent.

## S3 · Attleboro water

**M13 · UNKNOWN.** Both a copied output and a suppressed command are feasible. The recorded incident leaves delivery integrity unresolved. [Checked theorem](../paper_v2/formal_evidence/proof_records/v2_M13/specific_witness.kyp).

On the zero-output path, the trustworthy observer reports zero. The evidence implication holds, but the required positive evidence is absent.

## S4 · Attleboro water

**H0 · PROVED.** The operator is ready at tick zero. Exclusive Hand selection on generator power reaches sampled service and a fresh reading at tick three. [Checked theorem](../milestone2/evidence/proof_records/attleboro-local-hand-end-to-end-recovery-v1/end_to_end.kyp).

**H1 · REJECTED.** The required local operator is unavailable. The first assignment has no successor and the disabled box proves there is no complete execution. [Checked theorem](../milestone2/evidence/proof_records/attleboro-hand-dependency-mutations-v1/H1_disabled.kyp).

**H2 · REJECTED.** Readiness at tick one shifts the three scans to ticks two, three and four. The flow at tick three is 4 L/s, below the 5 L/s threshold. The terminal service sample is late. [Checked theorem](../paper_v2/formal_evidence/proof_records/v2_H2/specific_witness.kyp).

H1 has a concrete initial valuation, but its actor resource disables the first transition. H1’s postcondition rows are inapplicable after O2 fails. H2 reaches the positive terminal O5 and O6 predicates at tick four. O3 and the bound O7 contract require tick three.

## S5 · Merwin hydro

**MER0 · PROVED.** Under the pinned forcing and synchronization observations, contact closes and three fresh generation samples exceed the 1 MW threshold. [Checked theorem](../milestone2/evidence/proof_records/merwin-hcc-remote-auto-end-to-end-recovery-v1/end_to_end.kyp).

**MER6 · REJECTED.** The controller demands closure but stipulated inoperative contact stays open. The reduced plant reaches three zero-generation samples. [Checked theorem](../paper_v2/formal_evidence/proof_records/v2_MER6/specific_witness.kyp).

**MER10 · UNKNOWN.** The widened breaker relation admits contact and no contact. The no-contact execution violates service, while incident integrity remains unresolved. [Checked theorem](../paper_v2/formal_evidence/proof_records/v2_MER10/specific_witness.kyp).

On the zero-output path, the trustworthy observer reports zero. The evidence implication holds, but the required positive evidence is absent.

## S6 · Polish CHP

**CHP0 · UNKNOWN.** The fixture records a simulated device lifecycle with an independent benign runtime observation. Process readiness, physical production and customer delivery remain unresolved. [Device observations](../milestone2/chp_device_evidence.json).

## Reproduction

From the implementation repository, run the following command. The optional table argument writes the proof-to-claim table into the adjacent paper checkout.

```sh
python3 -m recovery_experiment.procedure_formalism.paper_v3.representative --table ../redundancy-analysis-paper-dsn-27/figures/proof-claims-v3.tex
```
