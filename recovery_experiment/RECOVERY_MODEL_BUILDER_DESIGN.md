# Recovery Model Builder Design

## Purpose

`recovery_model_builder.py` constructs only the synthetic parallel-pump family
`T1 -> {P1, P2} -> T2`. It is not a strategy synthesizer, a generic CPS
language, or a certificate issuer. Its purpose is to make the recovery game
shape explicit before selecting a reviewed theorem or attempting a new proof.

## A. Fixed Plant Model

The fixed state is `x1`, `x2`, P1/P2 command and effective states, isolation
state, flow variables, transition clocks, and resource budget. Every generated
physical phase uses:

```text
x1' = qin - q1 - q2
x2' = q1 + q2 - qout
```

Safety is the closed tank region `L1 <= x1 <= H1` and `L2 <= x2 <= H2`.
During flowing startup, `qin=startupInflow` and
`qout=qdelivered=startupWithdrawal`. Post takeover sets
`qin=demand=qout=q2=qbackup`, making both derivatives zero.

## B. Incident Model

The typed `ParallelPumpRecoverySpec` derives the recognized schedule from a
validated `RecoveryContext`:

| Incident | Effective-isolation time | P1-effective control intervals | P2 availability |
| --- | --- | ---: | --- |
| Immediate reviewed baseline | `0` | `0` | `2*ControlPeriod` |
| One period reviewed generated theorem | `ControlPeriod` | `1` | `3*ControlPeriod` |
| Two periods reviewed baseline | `2*ControlPeriod` | `2` | `3*ControlPeriod` |
| General bounded schedule | `n*ControlPeriod` | `n` | `m*ControlPeriod`, for integers `m>n>=0` |

The representation distinguishes an isolation request from an effective
isolator. While pending, P1 remains both commandable and physically effective.
After effective isolation, a Demon P1 command may still occur but `q1=0`.
P2 similarly distinguishes startup pending from available.

## C. Recovery Policy

The fixed flowing policy starts trusted isolation and P2 concurrently, preserves
startup inflow/withdrawal, activates P2 exactly at `StartupDelay`, deducts the
isolation-plus-backup cost once, and requires a positive mandatory `T`
operation phase. The builder emits no `*` loop and no optional transition.

Each `RecoveryPhase` records entry updates, owner, duration, dynamics, exit
test, safety/service obligations, commandability, and physical effectiveness.
The generated order is: attacker command, isolation request, mandatory pending
ODE interval(s), effective isolation, post-isolation attacker command,
mandatory backup-pending ODE interval(s), P2 availability, mandatory operation.
For every positive `n`, the builder emits exactly `n` attacker-effective
control intervals and a fresh Demon command before each one. New generalized
schedules emit exactly `m-n` backup-pending intervals. The legacy reviewed
`1T/3T` and `2T/3T` games preserve their original one-ODE backup segment with
an exact duration of `2T` and `T`, respectively, so their reviewed artifacts
remain byte-for-byte reconstructible after whitespace normalization.

Immediate isolation has the same semantic stages except its effective-isolation
transition is zero-duration and precedes its one startup ODE.

## D. Formal Contract

For every positive-delay schedule, the builder derives the endpoint margins
from the actual `IsolationDelay=I` and `StartupDelay=S`:

```text
x1 + startupInflow*S <= H1
x1 + (startupInflow-qprimary)*I >= L1
x2 - startupWithdrawal*S >= L2
x2 + (qprimary-startupWithdrawal)*I <= H2
```

The first and third bounds cover a P1-off direction through full startup; the
second and fourth cover P1-on while it remains effective. The precondition also
requires `qprimary >= startupInflow`, `qprimary >= startupWithdrawal`,
`startupWithdrawal >= qmin > 0`, `qbackup >= qmin`, startup by the transfer
deadline, and a sufficient intervention budget. Immediate isolation needs only
the full-startup T1-upper and T2-lower margins because P1 is never effective in
its startup ODE.

The installed CLEO parser treats `++` as Angel choice before a surrounding
dual. Therefore `{{ off ++ on }}^@` is the existing Demon binary command
encoding. Ordinary ODE braces are Angel-duration ODEs bounded by clock domains.
The builder uses explicit exit tests to force every phase to reach its exact
duration. It intentionally avoids `*`, whose loop semantics permit zero
iterations.

## E. Proof Profile And Artifact Boundary

The immediate and two-period outputs normalize exactly to their canonical
renderers. Their existing reviewed profiles and manifests therefore remain the
only runtime-authorizing artifacts:

* immediate: `state_dependent_proof_profile.attach_state_dependent_profile`
* two-period delayed: `delayed-isolation-clock-relative-margins-v2`

The one-period model uses the separate generated profile
`one-control-period-clock-relative-margins-v1`. It instantiates the same
clock-relative margin *template* with `IsolationDelay=ControlPeriod`; this is
not reuse of the two-period proof artifact. Its successfully revalidated proof
is bound by `intermediate_delay_certificate_manifest.json`, so the exact
`1T/3T` shape has its own reviewed runtime certificate. Other generated
schedules remain `CERTIFICATE_REVIEW_REQUIRED` even when a local CLEO proof
record says `VERIFIED`.

## Reconstruction Rules

`build_recovery_problem` renders the immediate and two-period phase plans and
compares their normalized complete envelope text with the canonical renderers.
Only an exact normalized match sets `matching_verified_artifact=True`.
The one-period model is generated from the same phase plan and is bound to a
separate reviewed provenance manifest, not a canonical hand-authored envelope.
A parseable game, local proof record, or successful simulator trace never
authorizes another schedule shape.
