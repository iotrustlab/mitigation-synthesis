# Repeated dependency-encoding measurements

The workload holds the plant to one forced linear inventory update and one exact terminal reading. Each candidate makes two QF_LRA checks in one incremental Z3 session per configuration run. The first tests whether an execution is feasible. The second looks for a reachable violation of safety, positive service or the observation requirement. All candidates referencing a particular dependency read the same enable bit. The number of possible assignments to the compromised bits is a count of feasible valuations. It does not measure how many branches Z3 explores.

## Design and measurement

The [benchmark](../paper_v2/scaling.py) reuses the previous experiment's specification, encoder and decision rules. The 98 cells cross 8, 16, 32, 64, 128, 256 and 512 nodes with candidate counts through 16, compromise fractions through 50%, and low and high sharing. For a matched node-by-candidate trend at 25% compromise, 1, 4 and 16 candidates each use every node. An additional rotating design represents every pair of factor levels, with a complete cross-section at 64 nodes. High and low fanout coincide for one candidate and are represented once. Within a cell, node order and integer rounding of the compromised count are fixed.

A seeded schedule shuffles the cell order in each round. Five warmup rounds precede thirty timed rounds. Each run constructs the specification, encodes it, launches a new single-threaded solver process, parses the answers and classifies each candidate. The raw CSV records each stage and the complete interval. The experiment did not flush OS page caches or control page residency. The single logical CPU used by E1 is on a shared machine. A separately pinned process ran the fixed-case proof timings. The [environment manifest](../results/paper_v2/environment_manifest.json) records the CPU, memory, software, affinity and cache policy. There is no baseline measurement that isolates solver startup alone.

The [summary](../results/paper_v2/dependency_scalability_v2.json) reports a per-cell median and nearest-rank p95, both calculated solely from the 30 measured runs. The median interval uses the 10th and 21st order statistics. Its nominal coverage of 95.72% assumes independent stationary observations. Shared-machine jitter limits that interpretation. Additional GNU time measurements record solver-child peak RSS. They are separate from the primary timing distribution and exclude Python's memory.

| All nodes shared, 25% compromised | Median / p95 at 8 nodes | Median / p95 at 512 nodes |
| --- | ---: | ---: |
| One candidate | 9.80 / 10.20 ms | 23.00 / 24.17 ms |
| 16 candidates | 11.38 / 12.02 ms | 47.33 / 49.11 ms |

Across all 98 cells, 2,940 measured runs made 37,200 queries. Every warmup, measured and memory-probe solver output agreed with the independent finite-contract oracle. The largest measured encoding was 119,767 bytes. For the plotted 16-candidate series the median solver wall time including process startup rose from 10.81 to 37.69 ms between 8 and 512 nodes. The median specification and encoding times at 512 nodes were 7.24 and 2.37 ms, respectively. Separate medians need not sum to the median end-to-end time. For the same series, peak solver RSS was 29,952 KiB at 8 nodes and 32,000 KiB at 512 in each of three probes. Candidates on this slice have identical required resource sets. Lower-sharing cells change both the number of dependency references and their overlap. These results characterize the supplied one-step encoding and query workload. Measuring hybrid proof cost requires the separate case-archive experiment.

## Reproduction

The raw [repetition CSV](../results/paper_v2/dependency_scalability_repetitions.csv) retains all 490 warmups, 2,940 measured runs, and 18 memory probes. In `report` mode the script checks the schedule, every model hash and size, the expected solver answers and encoded verdict, the count of feasible valuations, and the timing identities. It computes the summary without consulting the clock. To reproduce the published numbers in a new directory, from the implementation repository root run

```sh
mkdir -p scaling-report
src=recovery_experiment/procedure_formalism/results/paper_v2
cp "$src"/dependency_scalability_repetitions.csv "$src"/environment_manifest.json scaling-report/
python3 -m recovery_experiment.procedure_formalism.paper_v2.scaling report --output scaling-report --figure scaling-report/scaling-v2.tex
cmp "$src"/dependency_scalability_v2.json scaling-report/dependency_scalability_v2.json
```

Fresh timings use `measure --output scaling-replay --cpu 12` with Java and Z3 on the executable search path and `KEYMAERAX_JAR` naming the release jar. Supply a logical CPU available on the replication machine. Timing results and raw CSV hashes will differ with machine load. The optional `--proof-cpu` and `--game-cpu` fields record the CPU assignments of the separate proof timing series.
