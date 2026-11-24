# Bounded Local Hand recovery

The local operator acts at the Hand panel with generator supply selected and ready. In the historical design, Loop 0110-1 distinguishes Hand, Off and Remote. Loop 0128-1 permits generator-powered operation in Hand. The research simulator requires Hand selected, Remote deselected, a local operator present and an asserted local Hand demand. The power source, hardwired protection, VFD, pump, forward-flow path and observer serve both command locations. The local sequence has no PLC Remote request or PLC acceptance stage. The stage called `controller` in the common stage vocabulary here denotes the drive's local-mode acceptance. [Source-to-model map](../../attleboro/source_to_model_map.md)

## Contract

At request origin the fixture assumes a qualified actor is present, authorized and ready at an accessible panel. The stabilized generator supplies motor power. The pump starts stopped, actual and observed flow start at zero, and pH and protection inputs remain normal. Flow passage, the shared equipment and the meter retain their nominal relations for three 100 ms scans. Actor timing, timing of generator availability, sampling, plant parameters and pressure interpretation are research assumptions.

Under these conditions, for every execution of the issued Hand demand, the following conjunction holds.

```text
safe at origin and all three samples
and elapsed ticks = ready tick + 3 <= deadline tick 3
and pump running
and physical flow >= 5 L/s, pressure <= 90 psi, trip clear, pH in range
and fresh trusted reported flow and pressure equal their physical values
and service established.
```

The fixture's sampled safety bounds are 0–10 L/s and 30–90 psi. The first scan advances the startup delay, the next two produce flow samples of 4 and 6.4 L/s. Pressure reaches 49.2 psi at the third sample. The separate precondition and complete-execution witnesses ensure progress to a reachable service state. Five prefix obligations cover actor, local acceptance, delivery, plant and observer. The composed box and two witnesses bring the positive total to eight. The Local Hand archive has its own formal identity and reuses the generic Milestone 1 guarded assignments, dependency treatment, plant, observer, prefix renderer and tactics. [Generated profiles](../milestone2/hand.py)

The source-bound synthetic late-Hand bundle contains a three-row local startup from zero with flow samples 0, 4 and 6.4 L/s and Remote output off. The timely-Hand trace starts the corresponding segment with residual flow. These observations support the command/plant correspondence. Their actor arrival ticks are properties of those runs. The bounded theorem selects a new request origin with a ready actor, and H2 moves readiness one tick later while retaining the same deadline. The separate actor-interface study uses a longer illustrative access and response budget. Actual staffing, operator travel times, calibration, continuous behavior between samples and current site service remain unresolved.

## Applicability and mutations

The nominal Remote and Hand drive relations each require its own exclusive selector pair. The domain proof asks whether the two actual drive guards can both permit drive enable in one fixed selector state. Their intersection is empty even when both inputs request delivery. The nominal Hand theorem supplies a reachable generator/Hand state, and the Milestone 1 Remote theorem supplies a reachable utility/Remote state. A mode-change procedure would require different transition semantics and its own time and authority model. The two fixed-mode procedures have no common admissible cost context.

H1, H4, H5 and H10 disable required branches through loss of local actor, shared VFD, shared pump and shared motor power. Their negative boxes exclude any execution. H2, H3 and H6–H9 have reachable witnesses that violate the full contract due to lateness, invalid mode, trip, blocked flow, stale sample and observer compromise. The mutation classifications use the same IR and include an explicit witness or failed prerequisite. The B3 Remote PLC check is inapplicable to Hand. [Mutation results](../results/milestone2/attleboro_hand_mutations.json) · [Applicability domains](../results/milestone2/attleboro_domain_overlap.json)
