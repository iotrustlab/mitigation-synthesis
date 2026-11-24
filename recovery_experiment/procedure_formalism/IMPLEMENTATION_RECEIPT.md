# Implementation receipt

## Starting state

| Item | Value |
| --- | --- |
| Initial checkout | `main` at `2c0d35c3ccbbc58a7e086cd12b8199b7f41dbea9` |
| Staged, unstaged and untracked changes | None |
| Published prerequisite | `origin/codex/attleboro-procedure-bridge` at `bc8fd363750cfd4d244a604bebf42d06ffc4d026`, a direct descendant of the initial checkout |
| Implementation branch | `feature/procedure-aware-recovery`, created at the prerequisite commit |
| Remote | `origin`, GitHub repository `iotrustlab/mitigation-synthesis` |
| Other workspace repository | Paper checkout outside this change |
| Initial unit suite | System Python 3.10 could not import Draft202012Validator from its distribution copy of jsonschema. On main, discovery reported 149 tests, 1 import error, 12 skips. At the implementation base it reported 158 tests, 1 import error, 12 skips. |
| Resolved baseline | In an isolated Python 3.10 environment with jsonschema 4.25.1, the base's full discovery ran 173 tests, passing with 12 opt-in or dependency-gated skips. |

The initial bridge tree is `2d11d6d7990c5b958ac8c285e76262dd2a154ca9`. The SHA-256 of the sorted JSON mapping of paths to SHA-256 for all 174 base files is `f8e5e58e141106b724fa9ef16f35d03d016ea7936be3313e49b8deb3cec502a3`. The selected [historical digest inventory](historical_inputs.sha256) has SHA-256 `572e98ab551983af7a8f42d2913f53fe1b3affb6dc88b615b1e0260b90627dea`. All filenames in new records are relative to a repository or package root.

## Reproduction

Run commands from the mitigation repository root. The three SPHERE case subtree hashes in the [audit](CURRENT_ARTIFACT_AUDIT.md) and [case assessment](docs/CASE_INSTANTIATIONS.md) pin upstream evidence. Unit tests, bounded models and result generation use the checked-in package and its trace projection.

```sh
python3 -m unittest discover -s recovery_experiment/tests -v
sha256sum -c recovery_experiment/procedure_formalism/historical_inputs.sha256
python3 -m recovery_experiment.procedure_formalism.evaluation
python3 -m recovery_experiment.procedure_formalism.case_assessment
```

The historical one-scan proofs and original diamond witnesses were rerun into disposable output using KeYmaera X 5.1.1. With Z3 4.15.4 the two authority entries took 316 ms and 79 ms, and the two witness entries took 467 ms and 169 ms. The full invocations took 6.608 s and 3.162 s respectively. The [historical regression record](proof_records/historical_regression.json) contains commands, hashes and measurements. A prior run with Z3 4.8.12 also closed all four obligations but reported restricted startup lemma derivation. Raw historical transcripts and proof exports contain tool-generated machine paths and are retained outside this change. The canonical originals are covered by the inventory.

With a checkout of SPHERE matching the case tree, the following command reproduced all 22 correspondence matches. Set the two variables to the case directory and a disposable destination.

```sh
python3 -m recovery_experiment.attleboro.bridge --usecase-dir "$ATTLEBORO_CASE" --output "$CORRESPONDENCE_OUTPUT"
```

## Verified outputs

The [theorem and replay instructions](docs/ATTLEBORO_REMOTE_THEOREM.md) describe the three-scan Remote recovery formula. The [full proof summary](results/proof_summary.json) records nine positive obligations and eight mutation diamonds. The composed proof took 223 ms. The execution and precondition witnesses took 192 ms and 13 ms. The positive archive took 7.978 s including JVM startup. KeYmaera X reported restricted initialization of optional lemmas. Each required obligation closed and emitted its own proof artifact. The new proof index binds the original portable proof exports to the generated model bytes.

Exact execution was also checked against the pinned Python reference simulator for all 256 combinations of eight constant binary inputs over three scans. These inputs were pending reset, current reset, previous reset, generator mode, utility, blockage, meter freshness and trip. Per-scan flows and final output, run feedback, physical service, established service and observed flow agreed in each comparison. This bounded cross-check supplements the formal evidence.

| Deliverable | Location |
| --- | --- |
| Schema, Attleboro fixtures and dependency semantics | [procedure.py](procedure.py), [attleboro.py](attleboro.py), [dependency_semantics.py](dependency_semantics.py) |
| Formal IR, renderer and proof loader | [formal_ir.py](formal_ir.py), [formal_model.py](formal_model.py), [verify.py](verify.py) |
| Classification, four baselines and M0–M14 evaluations | [classifier.py](classifier.py), [evaluation.py](evaluation.py), [full matrix](docs/EVALUATION_MATRIX.md) |
| Post-admissibility cost and trace projection | [cost_vector.py](cost_vector.py), [nominal trace projection](fixtures/nominal_remote_cost_samples.json) |
| Merwin and CHP procedure schemas and result generation | [domain_cases.py](domain_cases.py), [case_assessment.py](case_assessment.py) |
| Formal inputs, proof exports and machine-readable outcomes | [models](models), [proof records](proof_records), [results](results) |
| Paper figures and source boundaries | [water figure inputs](docs/MOTIVATING_WATER_EXAMPLE.md), [framework](docs/FORMAL_FRAMEWORK.md), [case instantiations](docs/CASE_INSTANTIATIONS.md), [artifact audit](CURRENT_ARTIFACT_AUDIT.md) |
| Tests | Four new modules in the [existing test directory](../tests), with names beginning with `test_procedure_` |

The full deterministic suite ran 206 tests. 194 passed and 12 were skipped (11 opt-in historical CLEO regressions and one check requiring CLEO in the active interpreter). All 33 new tests passed. The seven result files regenerated byte-for-byte using the same proof records. All 174 base files matched their initial SHA-256 after validation, including all 76 protected files individually listed in the inventory. All milestone files are additions.

The Local Hand service proof, present-day site parameters, between-sample physical dynamics, instrument calibration and long-term plant service remain open. Merwin has trace evidence and lacks a complete recovery theorem. CHP lacks a process restart model and customer-service evidence. Active operator effort and motor energy remain unmeasured.
