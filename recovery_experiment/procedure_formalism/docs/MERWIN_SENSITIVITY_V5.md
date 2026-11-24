# Generation thresholds over the pinned Merwin research startup

The nominal HCC Remote Auto proof establishes three consecutive positive electrical samples by the original terminal poll. With the forcing, grid, synchronizing observations and trusted meter fixed, the greatest threshold met at all three polls is **15.540079 MW**. The original dL service guard is 1 MW. The other thresholds below are exact finite projections of the same guarded executions and numerical reduction. [Bound model](../milestone2/merwin.py) · [Arithmetic certificate](../milestone2/evidence/merwin_plant_reduction.json) · [Threshold intervals](../results/paper_v5/merwin_threshold_region.csv)

## Consecutive samples at a common deadline

Each query ends at tick 1296 and takes the last $k$ consecutive scheduled service polls. The physical requirement includes running and closed electrical contact. Each included reading must be fresh, trusted, equal to the generated power and at least the requested threshold. The query retains sampled safety, valid contact timing and the original terminal clock. For a branch satisfying these requirements the largest admissible positive threshold is the minimum of the included electrical outputs.

| Required consecutive polls | Poll ticks at 0.1 s per tick | Greatest positive threshold (MW, inclusive) |
| ---: | --- | ---: |
| 1 | 1296 | 15.85206398 |
| 2 | 1291, 1296 | 15.75840563 |
| 3 | 1285, 1291, 1296 | 15.540079 |
| 4 | Only three service observations exist | Unsupported |

These bounds use calculated electrical MW. The recorded forcing and synchronization inputs come from the pinned source projection. The case does not substitute observed site outputs for the calculated values. A smaller sample count changes the service contract by removing earlier polls while keeping the original deadline. Choosing $k=1$ therefore applies to the final poll. [Inputs](../milestone2/fixtures/merwin_remote_forcing.csv) · [Model and measurement provenance](MERWIN_FORMAL_CASE.md)

## Contact, evidence and scope

MER6 keeps contact open and produces zero MW at every service poll. It satisfies no positive threshold. MER8 reaches nominal electrical output but lacks a fresh final observation. Every suffix ending at that poll lacks evidence required for the combined contract. Under MER10 the guarded breaker admits both contact and no contact. Within the corresponding nominal threshold region this leaves service unresolved for the stipulated incident. Above that bound even the closed-contact branch misses the requested threshold, so every admitted execution violates the stronger contract under the pinned forcing. All three distinctions use every reachable terminal state. [Branch values and interval classifications](../results/paper_v5/merwin_threshold_region.json) · [Original case decisions](../results/milestone2/merwin_mutations.json)

The original arithmetic certificate verifies 1,296 100 ms updates on one input series. It fixes the gate and pressure forcing, synchronization telemetry, sampled times and grid assumptions. The input records supply individual values without justified ranges and joint constraints on hydraulic and synchronization perturbations. A forcing region would require these constraints and a new trajectory or invariance proof. The conclusion is a conditional startup theorem for the pinned research trajectory and its threshold projections. A physical installation or another trajectory requires independent input evidence.
