# Adaptive recovery after observed dependency loss

This controlled addition asks whether an operator with a truthful dependency observation can always choose a recovery that establishes the water contract. The historical water, hydro and CHP cases and the controlled fixed-procedure cost proofs retain their original semantics.

## Ownership and resource assumption

The archive is [water_game.kyx](../paper_v2/game_evidence/models/water_game.kyx). In a dGL diamond, ordinary finite union is Angel's choice. A finite union of deterministic assignments under dual gives Demon that choice. KeYmaera X spells the dual `^@`. The dual covers only the resource assignment. The defender's subsequent union is outside it. The game has neither repetition nor a player-controlled evolution duration. These interpretations follow Section 2, especially Definitions 2.5 and 2.6 of [Platzer, Differential Game Logic](https://symbolaris.com/pub/dGL.pdf) and the proof tool's bundled games examples.

Demon first assigns triples (P2-specific availability, P3-specific availability, shared power). The positive game enumerates (1,1,1), (0,1,1), and (1,0,1). Observation copies the two effective powered availability bits to distinct readable variables. The defender may choose P2 or P3 if its observation is one. Hold is always executable and delivers zero flow. The three positive disturbance choices are legal, total assignments. Hence no adverse state disappears through a failed test before the defender's turn. The shared-power extension gives Demon a fourth choice, (1,1,0), which sets both effective availability bits to zero. The observation mechanism and all subsequent transitions are the same.

## Physical contract and bridge to the water benchmark

The isolated primary supplies zero. Starting at 12 L, the tank receives 1 L/s and must stay in [4,17] L. The selected procedure passes its full mandatory startup interval, followed by a constant-delivery interval ending at four seconds. Flow must be at least 2 L/s continuously from the two-second deadline and a fresh, trusted terminal reading must equal that flow. Once active, either backup delivers 3 L/s. Local and automatic startup delays are respectively two seconds and one second.

The fixed-procedure dL rate-integral obligations establish the exact constant-rate volume maps and within-phase bounds from the endpoints. Both bridges and their certificates are identified in [the machine-readable game result](../results/paper_v2/adaptive_game.json). The game checks the two endpoint updates directly. Under P2, volumes at startup completion and horizon are 13 and 7 L. Under P3 they are 14 and 10 L. Holding gives 12 and 16 L, a credible reading of zero, and a missed service contract. Each case consumes the entire four-second horizon. Intermediate process dynamics, reporting delays and resource changes after observation are outside this game.

## Checked outcomes

| Archive entry | Checked formula and interpretation |
| --- | --- |
| `adaptive_win` | A dGL diamond proves existence of a service-preserving policy for all three resource choices, assuming observed health and a functioning shared power feed. |
| `fixed_P2_no_win` | Negation of the same diamond with the defender restricted to P2. Demon can remove its path. |
| `fixed_P3_no_win` | Corresponding negative theorem for fixed P3. Demon can remove its distinct path. |
| `shared_power_no_win` | Negation of the full adaptive winning diamond for the extended disturbance set. With common power removed, hold is still legal and its terminal flow is zero. |

The finite [strategy table](../results/paper_v2/adaptive_game.json) checks each legal action. Choose the sole powered backup when only one survives. In the both-available state either backup satisfies the contract. One may apply the separately verified policy-point comparison in that state. The game proves no cost-optimality theorem and assumes the dependency reporter and terminal flow observer are trustworthy.

## Replay

The source of the archive is [game.py](../paper_v2/game.py). It reads delay, capacity and tank parameters from the common fixed-procedure context. With the pinned proof environment, set `KEYMAERAX_JAR` to the release jar and place Java and Z3 on the executable search path. From the implementation repository root run

```sh
python3 -m recovery_experiment.procedure_formalism.paper_v2.game prove --output game-replay --result game-result.json
python3 -m recovery_experiment.procedure_formalism.paper_v2.game report --result regenerated-game.json
cmp regenerated-game.json recovery_experiment/procedure_formalism/results/paper_v2/adaptive_game.json
```

The first command creates fresh proof records. The second regenerates the report from the published [proof index](../paper_v2/game_evidence/proof_index.json) and original KeYmaera X exports, verifies the saved theorem text and hashes, checks the two fixed-procedure dL references and cross-checks the endpoint maps against their executable plans. Fresh tactic times can vary. Formal timing repetitions are reported separately.
