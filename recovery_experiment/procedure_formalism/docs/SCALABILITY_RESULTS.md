# Dependency encoding scalability

The full factorial design spans 8, 16, 32 and 64 distinct dependency nodes, 1, 2, 4 and 8 candidates, 0%, 10%, 25% and 50% requested compromise, and low, medium and high fanout. It produces 192 labeled cells, 720 candidate assessments and 1,440 SMT queries. With one candidate all fanout levels coincide. With two candidates low and medium coincide. The recorded fields give actual fanout and rounded integer counts for each cell.

Each candidate uses typed shared dependency objects. The unchanged finite dependency compiler determines whether each enable signal is nominal or can take either Boolean value. One symbol per resource preserves correlation across candidates. Final volume equals initial volume plus delivered flow over one mandatory tick. A trusted meter samples final volume. Each candidate asks for a feasible execution, then searches for a violation of safety, positive volume and credible observation. A satisfiable violation excludes the candidate and an unresolved solver response yields UNKNOWN.

| Nodes | Encoded bytes, min–max | Max joint valuations | Queries | Median spec generation (ms) | Median rendering (ms) | Median solver wall (ms) | Median classification (ms) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 | 758–3,097 | 16 | 360 | 0.158 | 0.066 | 8.737 | 0.0031 |
| 16 | 1,224–4,145 | 256 | 360 | 0.162 | 0.095 | 8.780 | 0.0031 |
| 32 | 2,168–6,287 | 65,536 | 360 | 0.234 | 0.145 | 8.498 | 0.0029 |
| 64 | 4,056–10,575 | 4,294,967,296 | 360 | 0.322 | 0.239 | 9.239 | 0.0028 |

A cell starts one Z3 4.15.4 process with a ten-second solver budget. Its wall time includes startup and both queries for each candidate, using incremental assertion scopes. Classification measures interpretation of the returned decisions. Across all cells wall times ranged from 7.84 to 11.17 ms, with no timeout or unknown outcome in this run. The largest configuration has 32 compromised nodes and represents 2³² joint signal valuations. Symbolic encoding avoids explicitly listing them. These counts do not measure how many assignments the solver visited.

The experiment isolates encoding and decision costs with one fixed, linear plant step. The measurements do not predict the proof cost of nonlinear hydraulics, longer horizons, changing disturbances or a physical plant of this size. The [machine-readable results](../results/milestone2/scalability_results.json) contain per-cell timings, query results, hashes, branch counts and actual shared-resource references.
