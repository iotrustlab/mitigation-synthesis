# Bounded Isolation-Schedule Contract

## Scope

`recovery_model_builder.py` supports the synthetic fixed-policy topology
`T1 -> {P1, P2} -> T2`. It does not model a physical installation, synthesize a
controller, or authorize a recovery from a simulation result.

The timing representation is the exact integer tuple:

```text
ControlPeriod = T > 0
isolation_periods = n >= 0
startup_periods = m > n
IsolationDelay = n*T
StartupDelay = m*T
```

The builder derives `n` and `m` from decimal-preserving rational ratios. A delay
that is not an exact integer multiple of `T` is unsupported; it is never rounded
to a nearby schedule.

## Generated Phases

For every positive `n`, the builder emits an initial Demon P1 choice, then exactly
`n` attacker-effective intervals. Each interval has its own Demon choice,
physical P1 effect, bounded ODE, and exact boundary test. For `n=0`, trusted
isolation is effective before startup and a generated noncanonical `(0,m)`
envelope explicitly records `IsolationDelay=0*ControlPeriod` and
`StartupDelay=m*ControlPeriod`. Trusted isolation then sets `q1=0`; later P1
commands remain logical attacker choices but have no primary-path effect.

For newly generalized schedules, the builder emits exactly `m-n` mandatory
backup-pending control-period ODEs. P2 becomes available only after the final
one. The old reviewed `1T/3T` and `2T/3T` models retain their single exact
backup-pending ODE so their existing reviewed text/provenance is preserved; its
duration is respectively `2T` and `T`. Every generated game has a mandatory,
positive post-takeover ODE and no repetition operator.

## Safety Derivation

During startup, `qin=startupInflow=a` and
`qout=qdelivered=startupWithdrawal=w`. Before isolation, P1 flow is either
`q1=0` or `q1=qprimary=P`; after isolation it is zero. The sufficient initial
conditions for any supported positive-delay schedule are:

```text
x1 + a*S <= H1
x1 + (a-P)*I >= L1
x2 - w*S >= L2
x2 + (P-w)*I <= H2
```

where `I=n*T` and `S=m*T`. The proof requires `P >= a` and `P >= w`.
The first and third bounds cover the extremal P1-off derivatives through the
full startup duration; the second and fourth cover the P1-on derivatives while
P1 can still be effective. Because each binary command produces a derivative
between those endpoint derivatives, arbitrary switching at every modeled
boundary is covered. After isolation, `q1=0`, so the remaining full-startup
conditions preserve the bounds through P2 availability. Safety is proved by
invariants and postconditions, not inserted into ODE domains to exclude unsafe
executions.

## Generated Proof Profiles

`bounded_delay_proof_profile.py` creates one pending-isolation invariant per
attacker-effective interval, then one backup-pending invariant per generated
backup interval and one operation invariant. For a noncanonical immediate
schedule it instead creates the direct startup and operation invariants. Its
positive-delay pending invariants carry the remaining-time forms:

```text
x1 + a*(S-startupClock) <= H1
x2 - w*(S-startupClock) >= L2
x1 + a*(I-isolationClock) <= H1
x1 + (a-P)*(I-isolationClock) >= L1
x2 + (P-w)*(I-isolationClock) <= H2
```

The tactic is `implyR(1); solve(1); QE`. A generated profile is only an
annotation template; `verify_bounded_delay_recovery.py` must independently run
CLEO to determine whether a particular theorem is verified.

## Review And Runtime Authorization

The runtime distinguishes construction, reviewed theorem provenance, certificate
review, and context coverage. A successful CLEO result alone never authorizes a
policy.

| Schedule | Artifact state | Runtime authorization |
| --- | --- | --- |
| `0T/2T` | Existing reviewed immediate theorem | Existing certificate checker |
| `1T/3T` | Generated theorem, fresh proof record, reviewed local manifest | `intermediate_delay_certificate.py` |
| `2T/3T` | Existing reviewed delayed theorem | Existing delayed checker |
| Other `(n,m)` | Constructed; may have an offline proof record | `CERTIFICATE_REVIEW_REQUIRED`, never selectable |

The `1T/3T` manifest binds the builder identity/version, exact schedule,
generated-envelope digest, proof source/profile/verifier hashes, exported proof
record, obligations, and safety/service/budget/finite-horizon contract. It is a
local provenance check, not an external signature, an independent proof checker,
or evidence that a deployment has trusted physical isolation.

The generic `(0,m)` path is a generated immediate-isolation model rather than a
replacement for the canonical reviewed `(0,2)` artifact. It is constructed with
its exact timing, but it remains unverified and unauthorized unless it receives
its own successful proof and separate review.

## Reproduction

```bash
# Run from mitigation_synthesis with CLEO's Python interpreter
"$CLEO_PYTHON" -m recovery_experiment.verify_intermediate_delay_recovery \
  --output-dir recovery_experiment/proof_records/intermediate_delay_1t

"$CLEO_PYTHON" -m recovery_experiment.verify_bounded_delay_recovery \
  --isolation-periods 3 --startup-periods 4 \
  --output-dir recovery_experiment/proof_records/bounded_3t4

"$CLEO_PYTHON" -m recovery_experiment.verify_bounded_delay_recovery \
  --isolation-periods 3 --startup-periods 5 \
  --output-dir recovery_experiment/proof_records/bounded_3t5

python3 -m recovery_experiment.bounded_schedule_evaluation \
  --output recovery_experiment/results/bounded-schedule-evaluation.json
```
