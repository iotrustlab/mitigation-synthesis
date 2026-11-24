# Fixed recovery procedures and assurance obligations

The formal unit is one supplied procedure in one incident. A dL box ranges over its permitted completed executions. A diamond has an existential interpretation. The same actor, status map, environment, initial values, horizon and threat alphabet bind the box and the execution witness. Selection under changed policy coefficients occurs after these checks.

## Definitions and equation correspondence

| Paper object | Meaning and implementation |
| --- | --- |
| Input and typed procedure | The graph shares resource identity across procedures. The incident attaches a dependency status to each node, separately from the evidence for assigning that status. The record in `procedure.py` binds actor, interface, controller, delivered output, actuator, process, observation and service to the hard contract and timing. |
| Hybrid-program syntax | Assignment sets a value, nondeterministic assignment admits any real, a test filters a transition, union is relational union, sequence composes relations and finite repetition includes zero iterations. ODE evolution follows its vector field within the evolution domain. The timed procedure fixes its phases separately. `formal_ir.py` lowers finite guarded assignments, and `milestone2/cost.py:rate_integral` supplies the continuous phase theorem. |
| Dependency-sensitive composition | `dependency_semantics.py:transition` transforms the nominal relation. Trusted resources use that relation, compromised ones use only a declared alphabet, unavailable required resources have an empty relation, and unknown resources permit both nominal and adverse values. The plant still constrains subsequent states. `formal_model.py:build_model`, `milestone2/merwin.py:model` and `milestone2/cost.py:plans` bind the ordered stages. In a direct local path the controller slot denotes the local guarded decision. |
| Service contract | Physical service and credible observation are separate conjuncts. Water requires sampled flow, run, pressure and interlock conditions with a matching trusted, fresh final reading. Hydro uses three credible generation samples and an ordered contact time. Controlled water requires timely sustained delivery and a fresh matching final reading. The CHP device record cannot supply the missing process and customer terms. |
| Classification and cost | A known failed prerequisite excludes a candidate. A feasible violating execution refutes a guarantee in the stipulated incident. An adverse choice existing solely because integrity is unknown leaves incident recovery unresolved. A proof failure alone leaves the outcome unknown. See `classifier.py`, `milestone2/merwin.py:_report` and `milestone2/chp.py`. The cost selector in `milestone2/cost.py:certified_selection` considers only proved procedures under an identical contract and context. |

## Theorem and proof boundary

For an applicable procedure, let Γ give its admitted initial states, D its scheduled boundary, and F an explicit persistent failure if the model uses one. The stage postconditions must establish the next stage's premises on every admitted branch. A reachable prefix cannot be silently filtered out after nature has made its choice. Each such prefix must extend to the boundary or to F, and a positive-service theorem must exclude F on all admitted executions. With accumulated safety, physical service through the contract interval, and production of credible evidence at assessment, sequential composition gives Γ → [α](safety ∧ physical service ∧ credible observation). Premise satisfiability and a diamond establish genuine execution. A universal implication from reported evidence to physical service alone cannot establish that an observation was produced.

The finite-stage renderer uses fresh slots plus a joint test for their guarded defining relations. The semantic choices are the guarded values supplied by each stage, rather than arbitrary valuations of internal existential slots rejected by the joint test. Nonblocking is checked for each reachable prefix in this finite semantics. The case archives bind the final clock and separately check nonvacuity. A timed hold or a suppressed command must still advance the contract clock. A missing resource may disable a procedure before admission. The proposition about controller correctness uses an existential execution of M5 in which the remote start output is one, its delivered value is zero and actual flow is still zero at the third scan.

## Evidence matrix

| ID | Required property | Formal interpretation and evidence |
| --- | --- | --- |
| O1 | Premises satisfiable | A concrete initializing assignment reaches Γ. The controlled cases use a witness with nonnegative weights. The universal case theorems still quantify over every nonnegative weight vector. |
| O2 | Nonvacuity | Γ → ⟨α⟩true follows from the previously proved stronger diamond with the successful terminal postcondition. |
| O3 | Progress | Every admitted finite prefix has a successor; all terminal states reach the scheduled boundary or an explicit persistent failure. The positive profiles contain no failure sink. We check prefix totality for the actual guarded transitions and prove the clock equation on the same program. |
| O4 | Safety | The existing composed proof includes the accumulated sampled safety flag (water, hydro) or bounded tank volume (controlled water, with its separate constant-rate ODE lemma). |
| O5 | Physical service | In the successful profiles the end-to-end box proves the physical predicate without a failure exemption. |
| O6 | Evidence correspondence | A new full-program box relates the observation flag to fresh, trusted, matching physical samples. It separately establishes evidence production under nominal assumptions. In controlled water the terminal sample alone cannot certify *earlier* sustained delivery. O5 establishes that time interval. |
| O7 | End-to-end hard contract | The original composed full-program box is checked by identity against its archived proof export. Its conjuncts establish the hard-safety, physical-service and evidence requirements together. |
| O8 | Conditional cost identity | The controlled archives additionally quantify over nonnegative weights and prove the cost component identities and weighted sum. The other cases have no common-context cost obligation. |

The machine-readable matrix identifies the source theorem, proof file, tactic duration and justified inference for each row. Source dL theorem identities remain in their original archives. Revision-specific dL projections and witnesses use distinct theorem names. Concrete calculations of bounds, stage clocks, hydro forcing and cost are traced in the six case records and in the cited original case reports.
