# Cross-domain results

## RQ1. Which apparently usable procedures have end-to-end assurance?

| Study | Labeled scenarios | Candidate assessments | B1 retained | B2 retained | B3 retained | B4 proved | B4 rejected | B4 unknown |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Attleboro Remote study | 15 | 21 | 19 | 12 | 7 | 1 | 19 | 1 |
| Attleboro Local Hand | 11 | 11 | 10 | 7 | 0 | 1 | 10 | 0 |
| Controlled water | 8 | 16 | 16 | 11 | 7 | 7 | 9 | 0 |
| Merwin HCC | 11 | 11 | 10 | 7 | 7 | 2 | 8 | 1 |
| Polish CHP | 9 | 9 | 8 | 7 | 5 | 0 | 5 | 4 |
| **Total** | **54** | **68** | **63** | **44** | **26** | **11** | **51** | **6** |

B1 checks component availability, B2 checks static availability along the path, and B3 stops at the controller boundary. The HCC controller-only check conditions the close sequence on an at-speed input after acceptance. It does not independently establish the physical shaft speed. B3 is inapplicable to a direct local panel with no Remote PLC. B4 requires a credible, bounded physical outcome. Among assessments retained by B1, B2 and B3, respectively 52, 33 and 19 lacked end-to-end assurance. The union across all three contains 53 distinct assessments. These are decisions on selected scenarios. Several rows query the same trace or include multiple candidates. The counts do not estimate incident prevalence or independent field error rates. [Full per-procedure decisions](../results/milestone2/cross_domain_baselines.json)

Three cases show where the difference arises.

- **Attleboro M5.** The PLC sets its start output to one. A reachable downstream delivery of zero leaves the pump stopped. Three scans later, physical flow remains zero. B3 accepts the controller prefix and B4 rejects the requested recovery.
- **Merwin MER6.** The sequence reaches a permitted close command. The contact mutation prevents electrical connection, and the three generated-power samples fail the research service requirement. B3 accepts the command and B4 rejects. In MER7 contact closes but generation coupling fails.
- **CHP0.** A reviewed, compatible backup and a disposable OpenPLC heartbeat establish bounded device execution. Process permissives, physical output and the external customer-supply mechanism are unresolved. B4 returns UNKNOWN for recovery. The explicitly unready CHP6 case excludes the process procedure even though device recovery can succeed.

## RQ2. Which deep recovery contracts close?

The five nominal cases discharge 34 dL obligations, including a universal end-to-end theorem and a reachable successful execution for each case. The new Hand, cost and Merwin families together discharge 49 dL obligations across nominal and mutation profiles. Eight of the 19 Hand-family obligations cover nominal Hand. Its ten mutations and a separate selector-disjointness theorem account for the rest. The cost family contributes 19 and Merwin contributes 11. Merwin additionally uses a Z3 certificate for the 1,296-scan plant reduction.

| Procedure | Obligations proved | Horizon | Controller / plant / composition tactic time (ms) | Whole archive (s) |
| --- | ---: | --- | --- | ---: |
| Attleboro Remote regression | 9 | 0.3 s | 23 / 275 / 216 | 8.008 |
| Attleboro Local Hand | 8 | 0.3 s | 18 / 165 / 189 | 7.563 |
| Controlled P2 | 5 | 4 s | 15 / 47 / 88 | 7.164 |
| Controlled P3 | 5 | 4 s | 22 / 48 / 104 | 3.158 |
| Merwin HCC Remote Auto | 7 | 129.6 s | 20 / 297 / 316 | 8.703 |

Times refer to the saved measurement records, including the pre-experiment replay for Remote. Archive totals include JVM startup. Prefix measurements include earlier stages. The separate hydro arithmetic certificate checks a reduced, fixed-input trajectory. The KeYmaera X hydro theorem then uses that checked reduction to connect acceptance, rotor response, synchronization, breaker contact, actual generation and observation. Its guarantee is conditional on the recorded gate orders, hydraulic forcing, phase and voltage, plus the documented integer approximation. [Model sizes, state and dependency counts, rendering times and obligation results](../results/milestone2/rq2_summary.json)

## RQ3. What does a proved cost change?

On the common four-second water benchmark both paths meet the same safety and service contract. Nominal P2 has proved cost coefficients (3 L, 1 s, 0 manual actions, 12 J). P3 has (6 L, 2 s, 1 manual action, 2 J). Service-heavy weights select P2 by 39 to 57 policy points. Resource/intervention-heavy weights select P3 by 19 to 52. Equal declared per-unit weights select P3 by 11 to 16. Controller compromise leaves P3 alone, local actor loss leaves P2 alone, and loss of common power leaves neither. [All 24 policy and mutation selections](../results/milestone2/rq3_summary.json)

The historical water fixture's Remote and Hand selector conditions are disjoint, so the controlled cost ranking applies only to the separate benchmark. The release includes the [domain intersection proof](../results/milestone2/attleboro_domain_overlap.json) and [semantic reuse inventory](../results/milestone2/proof_reuse_results.json).
