# Review of the baseline, cost and timing evidence

The review starts from manuscript `fa2b6ce` and experiment `fa71938`. Both checkouts matched their fetched branches and were clean. The paper was eight body pages plus references. The original Figure 3 and Tables III–IV were checked against their source, rendered PDF and the individual cross-domain assessments, cost proofs and solver records before revision.

## Figure 3

One observation is a candidate procedure in one scenario. There are 68 observations across 54 scenarios. The four analyses see the same observations. B1 tests component availability, B2 tests the static dependency route, and B3 tests a controller output or CHP runtime. ACCEPT means the relevant prefix criterion holds. B4 supplies a stronger, modeled end-to-end reference contract. It has 11 proved, 51 rejected and six unresolved assessments. These are conditional engineering judgments, not field labels.

The entries below are triples in B4 order **proved / rejected / unknown**. All cells were counted from individual rows in `results/milestone2/cross_domain_baselines.json` under the experiment package. The in-scope nonretained category includes B2's two UNRESOLVED decisions. The union of retained assessments lacking assurance hides 47 contradicted and six unresolved assessments.

| Baseline | Applicable / 68 | Retained | Applicable, nonretained | Inapplicable | Proved omissions |
| --- | ---: | --- | --- | --- | ---: |
| B1 | 66 | 11 / 46 / 6 | 0 / 3 / 0 | 0 / 2 / 0 | 0 |
| B2 | 66 | 11 / 29 / 4 | 0 / 20 / 2 | 0 / 2 / 0 | 0 |
| B3 | 41 | 7 / 13 / 6 | 0 / 15 / 0 | 4 / 23 / 0 | 4 |

Both hold queries lack a positive-service component or path for B1/B2 to assess. B3 also excludes local Hand and controlled manual procedures without the relevant controller prefix. Four proved procedures are outside its scope. An accepted PLC output with suppressed delivery is a genuine witnessed contract disagreement. With unresolved delivery integrity the PLC criterion can still pass, whereas B2 itself returns UNRESOLVED. B4 cannot certify actual service on that evidence. A reviewer needs the reason for each difference to distinguish missed downstream failure, missing evidence and scope. The revision uses the same 68-row denominator with separate disagreement types and identifies the decisive stage.

## Table III

The original ordered cost vectors are P2 = (3 L, 1 s, 0 actions, 12 J) and P3 = (6 L, 2 s, 1 action, 2 J). The coordinates measure service deficit, subminimum-flow time, accepted manual actions and energy. Each coefficient is in policy points per corresponding unit. The two proofs share an initial tank, demand, horizon, deadline and meter contract. They support exact finite-choice accounting.

The supplied coefficients (8,3,1,1), (1,1,3,4) and (1,1,1,1) illustrate service priority, resource priority and unit coefficients. They lack stakeholder calibration or normalization. Giving the unit coefficients the name “balanced” implies a value judgment that the dimensions cannot support. Neither procedure dominates. P2's score is smaller exactly when 10 w_r < 3 w_s + w_t + w_i. Equality is a tie. At the three policies the signed P3-minus-P2 margins are +18, −33 and −5 policy points. The closest single-coefficient ties require respectively a 75% decrease in the service coefficient, an 82.5% decrease in the energy coefficient and a 50% decrease in the energy coefficient. A strict reversal needs a larger change in that direction. The revision checks these perturbations using exact arithmetic and separates exclusions caused by dependency loss from the weights.

## Table IV

The original 192 configurations used a single timed run each, including creation of a fresh Z3 process per configuration. Every candidate has a feasibility query and a contract-violation query over a single linear material-balance step. A process is reused across candidates in the configuration. The recorded solver-wall range, 7.84–11.17 ms, is the minimum and maximum across unlike cells, not a repeat distribution. Specification generation, encoding, solver wall and classification are distinct fields. That range described only solver wall. There was no CPU/RAM manifest in that measurement record, so the old run cannot be assigned a hardware configuration retrospectively.

Starting one solver for a short formula contributes a fixed cost, and the old configuration capped nodes at 64 and candidates at eight. Those design facts plausibly explain the small spread; one observation per cell cannot attribute it to a dominant cause. Query count grows with candidate count; fanout changes the number of dependency references, and compromised resource states affect the constraints and feasible valuations. The revision crosses those dimensions, times the phases separately and reports medians and p95 with repetitions and machine context. Finite dependency encoding probes neither nonlinear plant proof complexity nor a whole installation. The proof replay entries in the same old table concerned different tools, quantities and clocks. They require their own coverage and performance table.
