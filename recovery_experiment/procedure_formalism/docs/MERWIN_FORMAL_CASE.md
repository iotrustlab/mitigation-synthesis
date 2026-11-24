# Merwin HCC Remote Auto bounded research theorem

The historical HCC mode exercises a remote actor, a communication dependency, normal auxiliaries, automatic synchronization and a separate breaker contact. The source fixture has an OpenPLC capture of this complete sequence. Local Manual, Local Auto and no-start remain available as typed schema instances. The two local starts check guide-bearing lubrication and oil level. In the HCC branch the controller checks normal auxiliaries, remote selection, HCC presence, link availability and the HCC rising request. The nominal capture already has both local lube/oil indication bits low. MER3 removes the local lubrication indication and leaves the HCC theorem applicable. [Historical source assessment and identifiers](../../../PROCEDURE_EXPERIMENT_RECEIPT.md)

## Inputs and theorem

The model starts with a stopped representative unit. Its gates and shaft speed are zero, the breaker is open, and the HCC operator is ready when the recorded rising pulse arrives at 3.1 s. The aggregate plant start permissive denotes run enabled, no trip, open breaker, sufficient reservoir level and head. The HCC selector is exclusive. An admitted start enables a bounded gate sequence. An inhibited start holds the gates and shaft at zero. The hydro unit, breaker path and observer have separate operational states. Trusted nominal resources, a functioning generator coupling, persistent safe-state inputs and credible meter delivery are scenario assumptions.

The proof fixes a research reduction of the archived HCC rollout. The inputs are 260 recorded polls, projected to a 100 ms grid using time from the first capture row. They retain only gate setpoint, hydraulic pressure, voltage, phase and HCC start. The electrical bus is the simulator's 60 Hz, 1 pu ideal grid. Before grid contact, the model computes slip from its own rotor speed and combines it with the recorded phase and voltage at the observed polling instants. The relay and controller use their distinct source thresholds. This mixed timing and phase model conditions the result on a supplied forcing trajectory. [Projected inputs](../milestone2/fixtures/merwin_remote_forcing.csv)

For nominal input Γ, guarded program α and final elapsed tick 1296 the theorem is

```text
Γ → [α] (sampledSafe ∧ threePhysicalServiceSamples
         ∧ threeCredibleServiceSamples ∧ clock = deadline)
Γ → ⟨α⟩ (sampledSafe ∧ threePhysicalServiceSamples
         ∧ threeCredibleServiceSamples ∧ clock = deadline).
```

Safety bounds gate position to [0,100]% and shaft speed to [0,110]% at all modeled scans. The 110% limit comes from the surrogate controller trip threshold. Contact requires relay permission and a close demand. Every positive service sample requires the running state, closed contact and computed electrical output of at least 1 MW. The three observations must be consecutive source polls with fresh, trusted, matching power. The deadline is 129.6 s from the first stopped-state capture row. Timing, safety limits and MW thresholds apply only to this research fixture.

## Physical correspondence

Upstream case tree `e825cc0af6459044a5aef1ac84d6845ac4756b1e` identifies the Merwin inputs. The HCC trace SHA-256 is `7cfe891e497d6f27100f385ec7e19e4ca6d9face9077c1d1cd7ff1a14007b2fa`. The simulator SHA-256 is `cde204ba7a533f63b1b09df7f047cc3579822218ec7180b5b6f3c37f3d3b75ec`. The controller SHA-256 is `c8b74bd88e640ea2b2caf5f7eb4e94612c5d460c02f6bebfe0cfc9adecfcdaba`. The simulator and controller use a 100 ms period.

* The sampled gate servo moves one tenth of its position error per step, subject to a 10%/s slew limit and the [0,100]% clamp. A left-held recorded gate setpoint supplies the downstream demand after the procedure is accepted.
* Pressure supplies the turbine-head input. The orifice law gives Q = 10 × (gate/100) × √(pressure/9.81), capped at 100 m³/s. Mechanical MW equals 0.9 × Q × pressure/1000 with pressure in kPa. The gate, orifice and shaft equations are evaluated on a research fixed-point grid with six decimal places and downward integer rounding.
* With open contact and Q > 0.1 m³/s, the source Euler law advances rotor percentage by 0.1 × (mechanicalMW/8 − speed/50)/4. Otherwise shaft speed follows the coast law. The model counts 30 consecutive scans within 0.5% of synchronous speed, then evaluates every available synchronization poll. The source uses a 350 ms phase prediction, its own slip/voltage window, and separate plant relay limits. The first joint permitted poll occurs at 128.1 s.
* Stable close demand permits the simulator's 50 ms close timer to complete in one 100 ms scan. Successful contact locks the shaft to the ideal grid at 100%. The first service poll follows this contact opportunity. With the contact closed, electrical MW equals the mechanical input times generator efficiency 0.97, capped at the simulator's 80 MW rating. Open contact yields zero electrical MW. The reduced model computes approximately 15.540, 15.758 and 15.852 MW at ticks 1285, 1291 and 1296. The recorded values rounded to three decimals were 15.572, 15.721 and 15.851 MW. The capture records initial contact at 128.546346 s and the third sample at 129.576742 s relative to its first row.
* The first settled 30-scan window ends at tick 652. The calculated open-shaft speed at the synchronization poll is approximately 100.038%, with nominal phase −2.135° and generator voltage 1.03 pu. The full open trajectory peaks below 101% and the gate below 60%.

The input pressure represents the combined effect of reservoir and penstock dynamics. The profile excludes ten-substep water-column integration, governor feedback recomputation, excitation transients and closed-loop phase prediction between polls. It uses fixed-point arithmetic instead of OpenPLC floating point. It holds the positive contact through the three observations. A failed contact or uncoupled generator still yields zero generated MW even when the recorded gate order remains high. The result covers sampled initial generation under the given forcing and availability assumptions. Current station limits, dispatch, site response times, subsequent grid service and unconditioned progress of the full upstream simulator remain open.

## Proof, evidence and reuse

The [reduction checker](../milestone2/merwin_reduction.py) constructs a ground integer SMT refutation of any inconsistent trajectory step. It checks every slew/clamp, integer square-root bound, torque, rotor recurrence, sampled gate/speed safety limit and successive state link. It verifies the first 30-scan settled window, first jointly permitted sync poll, time-ordered service sample indices and three mechanical torque values consumed by the dL program. Stored results bind the forcing CSV, SMT input and numerical summary. Missing or mismatched arithmetic evidence blocks a positive classification. Nominal gate/torque specialization relies on the declared response to admitted demand and the stopped specialization for inhibited demand.

Five stage boundaries align with the water study. They cover the actor, controller acceptance, delivered actuator effect, physical service and trustworthy observation. The hydro model adds off-grid rolling/settlement and synchronization. The typed resource transition compiler, finite guarded assignments, exact execution, dL renderer and finite-stage proof tactic are shared. Gate/runner equations, HCC-specific authority, relay logic and sustained generation are case-specific. The seven nominal KeYmaera X obligations check actor/controller, roll/sync, delivery, plant, observation, universal composition and an executable progress witness. Four additional diamond proofs cover MER6, MER7, MER8 and the possible MER10 failure. [Mutation assessments](../results/milestone2/merwin_mutations.json) · [Proof summary](../results/milestone2/merwin_proof_summary.json)

Run from the repository root with the pinned Java, KeYmaera X and Z3 tools configured.

```sh
python3 -m recovery_experiment.procedure_formalism.milestone2.merwin_reduction
python3 -m recovery_experiment.procedure_formalism.milestone2.proofs merwin
python3 -m unittest recovery_experiment.tests.test_milestone2_merwin
```

To validate the projection against the hash-pinned upstream CSV, pass `--project "$HCC_TRACE_CSV"` to the reduction command. The normal replay uses the committed projection.
