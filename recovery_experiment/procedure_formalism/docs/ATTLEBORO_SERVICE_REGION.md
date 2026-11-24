# Water service thresholds and operator readiness

The nominal water fixture starts from a stopped pump and zero flow. An authorized operator is ready at tick $r$. The research contract assesses delivery once after $n$ mandatory 100 ms scans and requires completion no later than request-relative tick $D$. These queries compare different terminal schedules and minimum flows under the same nominal resources. [Exact water model](../formal_model.py) · [Region and endpoints](../results/paper_v5/attleboro_service_region.json) · [Grid](../results/paper_v5/attleboro_service_region.csv)

## Boundary under the sampled response law

The first powered scan has no running feedback. From the second scan onward the target on the unblocked path is 10 L/s. Applying the encoded gain of 2/5 gives $q_n=10[1-(3/5)^{n-1}]$ L/s for $1\le n\le3$. The clamp leaves the initial zero unchanged and the positive updates exceed its 0.01 L/s cutoff. The pressure at each scan is $30+3q_n$ psi. The origin and each retained update satisfy the encoded flow, pressure, trip and pH safety checks. The fresh trusted flow and pressure readings equal both physical values at the chosen assessment. The deadline is an upper bound on completion. A later deadline does not extend the time covered by an earlier terminal reading.

| Mandatory scans | Terminal flow (L/s) | Terminal pressure (psi) | Positive flow requirement at this assessment |
| --- | ---: | ---: | --- |
| 1 | 0 | 30 | None. The drive has yet to report running. |
| 2 | 4 | 42 | Any positive threshold at most 4 L/s, if $r+2\le D$. |
| 3 | 6.4 | 49.2 | Any positive threshold at most 6.4 L/s, if $r+3\le D$. |

For an enabled nominal procedure the full terminal condition is $n\ge2$, $0<m\le q_n$, and $r+n\le D$. At thresholds up to 4 L/s, the earliest eligible assessment among these schedules is tick $r+2$. For thresholds above 4 through 6.4 L/s it is tick $r+3$. No schedule in the checked prefix meets a higher threshold. In the archived three-scan, 5 L/s contract a Hand operator must be ready by $D-3$. H2 starts at tick one, has 4 L/s at the request-relative deadline of three and reaches 6.4 L/s at tick four. H1's unavailable actor disables the request stage and leaves its operational premise inapplicable. [Hand assessments](../results/milestone2/attleboro_hand_mutations.json)

## Verification and scope

The generator authenticates the original M0 and Hand proof records, then truncates the existing guarded plant assignments after the selected scan. It binds the original terminal flow, pressure, clock, run and safety slots to that endpoint, changes the physical and observed threshold consistently, and executes the same terminal meter stage once. This explicitly schedules a terminal read in each shortened procedure. The archived three-scan procedure has no intervening meter sample. An exhaustive exact-rational check establishes the queried terminal property or produces its violating endpoint. The original dL exports establish the original contract. The shorter schedules and new thresholds are derived finite-model results. [Generator](../paper_v5/regions.py) · [Remote theorem](../proof_records/M0/end_to_end.kyp) · [Hand theorem](../milestone2/evidence/proof_records/attleboro-local-hand-end-to-end-recovery-v1/end_to_end.kyp)

The reproducible grid crosses M0, H0, H1 and H2 with 1–4 requested scans, request-relative deadlines at ticks 2–4, and minima of 4, 5, 6.4 and 7 L/s. Each of the 192 rows records its inputs, completion tick, flow, pressure, sampled safety, meter match and result where defined. The fourth-scan row is an unsupported schedule. Its empty fields record the end of the model. A disabled actor has no endpoint. The thresholds and scan timing belong to the research fixture and supply no operating limit or staffing data for the historical installation.

Run `python3 -m recovery_experiment.procedure_formalism.paper_v5.regions` from the implementation repository to regenerate both sensitivity studies. An optional `--output` directory supports comparison with the published JSON and CSV.
