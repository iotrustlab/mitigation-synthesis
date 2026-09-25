# Delayed-Isolation Recovery Contract

## Scope and status

This is a separate, synthetic recovery problem. It does not alter the immediate-isolation theorems, certificates, envelopes, or policies. The attacker retains P1 command control until a trusted physical isolator becomes effective. The delayed symbolic theorem is **VERIFIED** in CLEO and is bound to the reviewed local certificate `two-tank-flowing-takeover-delayed-isolation-v1`.

The certificate is implemented by [`delayed_isolation_certificate.py`](delayed_isolation_certificate.py), with canonical provenance in [`delayed_isolation_certificate_manifest.json`](delayed_isolation_certificate_manifest.json). The checker accepts only that manifest, verifies its reviewed SHA-256 anchor and the hashes of the static envelope, renderer, proof profile, and offline verifier, then checks the concrete context. It never reruns CLEO, treats a simulator result as proof, or issues a control command. The local manifest is not externally signed and does not establish a physical deployment's independent isolation authority.

The model is the local two-tank topology `T1 -> {P1, P2} -> T2` with

```text
x1' = qin - q1 - q2
x2' = q1 + q2 - qout
```

`demand` is the requested downstream service, `qout` is physical withdrawal from T2, and `qdelivered=qout` is actual service supplied from T2 storage. Thus, zero instantaneous pump transfer does not imply zero delivery while T2 contains water. It also means inadequate P2 capacity can initially satisfy service while driving a tank out of its safety interval; that is not a sustained recovery guarantee.

## Exact first timing family

P2 startup and the trusted isolation command begin concurrently at time zero. For the first parameterized theorem family:

```text
ControlPeriod > 0
IsolationDelay = 2 * ControlPeriod
StartupDelay   = 3 * ControlPeriod
0 < IsolationDelay <= StartupDelay <= TransferDeadline
```

For the evaluated instance, `ControlPeriod=0.5`, `IsolationDelay=1.0`, and `StartupDelay=1.5` seconds.

1. At `t=0`, Demon chooses P1 off or on; isolation is commanded, P2 startup begins, and P1 remains physically connected.
2. At `t=0.5`, Demon chooses P1 off or on again. This is the second effective attacker command interval.
3. At `t=1.0`, trusted physical isolation becomes effective and forces `q1=0`. Demon may still issue a third P1 command, but it has no physical effect.
4. From `t=1.0` to `t=1.5`, P2 is still starting; `q1=q2=0`.
5. At `t=1.5`, P2 becomes available. The game establishes balanced backup operation and runs it for mandatory `T>0` time.

The certificate does not cover arbitrary delays, a third effective attacker decision period, or another attacker command frequency. At runtime, an optional trace schedule must name exactly the two pre-isolation off/on commands. A missing schedule means no favorable trace is assumed: the symbolic theorem covers all four pairs. The explicit third syntactic `p1` assignment in the game occurs only after `q1:=0` and physical isolation, so it has no flow effect and is not a certificate schedule input.

The simulator follows the same discrete ordering: attacker command, defender action, zero-delay transitions, flow calculation, Euler integration, monitoring, then delayed clock advancement. A transition reaching zero becomes effective at the next control boundary. Trace fields distinguish `isolation_commanded`, `isolation_pending_during_interval`, and `isolation_effective_during_interval`.

## State-dependent sufficient region

Let `a=startupInflow`, `w=startupWithdrawal`, `P=qprimary`, `B=qbackup`, `I=IsolationDelay`, and `S=StartupDelay`. During `0 <= t <= I`, Demon selects a binary `q1` of either `0` or `P` once per control period. Conservatively, `0 <= q1 <= P`, hence

```text
x1(t) <= x1(0) + a*t
x1(t) >= x1(0) + (a-P)*t
x2(t) >= x2(0) - w*t
x2(t) <= x2(0) + (P-w)*t
```

After isolation and before P2 is available, `q1=q2=0`, so `x1'=a` and `x2'=-w`. The contract imposes these sufficient conditions for both phases:

```text
x1 + a*S <= H1
x1 + (a-P)*I >= L1
x2 - w*S >= L2
x2 + (P-w)*I <= H2
P >= a
P >= w
B >= qmin > 0
w >= qmin
```

The first and third inequalities cover the worst P1-off direction through the entire P2 startup duration. The second and fourth cover P1-on behavior while it remains effective during the delay. The `P` capacity assumptions make each corresponding endpoint conservative. After takeover, the theorem sets `qin=demand=qout=B`, so `x1'=x2'=0` and service is `qdelivered=B>=qmin` for the required positive operation interval. The conditions are sufficient, not claimed necessary; in particular they conservatively cover all binary on/off schedules by the continuous interval `0 <= q1 <= P` in the ODE annotations.

The ODE evolution domains limit only time clocks and deadline timing. They do **not** contain desired tank-safety bounds; tank safety must follow from the precondition, dynamics, and proof obligations.

## Formal game and proof

[`delayed_isolation_recovery_takeover.envelope`](delayed_isolation_recovery_takeover.envelope) is the static formal artifact. [`delayed_isolation_formal.py`](delayed_isolation_formal.py) renders the same text, and [`delayed_isolation_proof_profile.py`](delayed_isolation_proof_profile.py) attaches separate invariants for phase one, phase two, backup pending, and mandatory operation. The game has no `*` loop, so it cannot skip a transition or the post-takeover interval.

The original profile incorrectly carried the four full-duration, initial-state margins into every later phase. That is not inductive: after the first P1-on interval, for example, `x1 + (a-P)*IsolationDelay >= L1` need not hold when interpreted using the *new* `x1`. The failed `be` and `bn` obligations were therefore failed proof attempts caused by an overstrong phase invariant, not timeouts, tactic syntax errors, unsupported operations, or counterexamples to the recovery game.

Proof profile `delayed-isolation-clock-relative-margins-v2` retains those four margins in the theorem precondition, but carries only their clock-relative forms during the ODEs:

```text
x1 + a*(StartupDelay-startupClock) <= H1
x2 - w*(StartupDelay-startupClock) >= L2
x1 + a*(IsolationDelay-isolationClock) <= H1
x1 + (a-P)*(IsolationDelay-isolationClock) >= L1
x2 + (P-w)*(IsolationDelay-isolationClock) <= H2
```

For `0 <= q1 <= P`, their derivatives are respectively `-q1`, `q1`, `-q1`, `P-q1`, and `q1-P`, with the appropriate upper/lower inequality directions. Thus they are preserved across each constant-flow ODE interval. A new Demon assignment may choose either endpoint for the next interval, but again establishes `0 <= q1 <= P`; all four off/off, off/on, on/off, and on/on schedules are covered.

The profile uses `implyR(1); solve(1); QE`. `solve(1)` exactly solves each linear constant-flow ODE and leaves a real-arithmetic duration witness; `QE` proves the required endpoint and time-domain facts. A differential-induction/differential-cut proof is possible in principle, but is not necessary for this linear game. The latest reviewed revalidation discharged phase-one `be`, phase-two `bn`, backup-pending `bu`, mandatory-operation `ch`, and top-level arithmetic `a`; milestones A--E all passed. The certificate manifest records the exact source hashes, verifier command, status, obligation identifiers, and measured offline run time. Its horizon clause is the theorem's actual range: `T>0`. A runtime evaluation horizon is bound as `T=horizon-StartupDelay`, so it must leave a positive post-takeover interval; a successful six-second evaluation is never used to infer a longer guarantee.

Reproduce the attempt from the repository root with a CLEO-enabled interpreter:

```bash
"$CLEO_PYTHON" -m recovery_experiment.verify_delayed_isolation_recovery \
  --output-dir recovery_experiment/results/delayed-isolation-formal
```

The command exits zero only when every delayed-isolation obligation is discharged. It proves the symbolic theorem; the separate runtime checker authorizes only contexts that also satisfy the reviewed certificate assumptions.

## Incident construction and evaluation

[`formal_problem.py`](formal_problem.py) first validates an incident and then selects the immediate state-dependent or delayed model. A positive explicit delay never falls back to the immediate theorem. The first delayed family is recognized only for `I=2*ControlPeriod` and `S=3*ControlPeriod`; other positive timings are reported as unsupported for reusable-proof purposes. Construction, theorem verification, certificate lookup, and applicability remain separate: the exact delayed family looks up only the delayed certificate, while a state or parameter violation is reported as `NOT_COVERED_BY_CERTIFICATE` rather than as a claim that no safe strategy exists.

Run the deterministic comparison with:

```bash
python3 -m recovery_experiment.delayed_isolation_evaluation \
  --output recovery_experiment/results/delayed-isolation-evaluation.json
```

It includes immediate baseline coverage, a certified delayed off/on schedule, T1 and T2 margin failures, insufficient backup capacity, timing outside the first theorem family, and missing trusted isolation. Simulation is diagnostic and is kept separate from formal coverage and cost reporting.

## Cost interpretation

For the default delayed instance, the nominal contract-minimum procedure cost is `8.875`: zero service loss, recovery duration `1.5`, intervention charge `2`, and backup usage `1.5*(6-1.5)=6.75`, with weights `(10,1,2,0.5)`. It is not a chosen-attacker or worst-case value: its zero service-loss term evaluates startup delivery against `qmin=1.2`.

The observed trace cost is `13.375` when it uses external demand `1.5` as its service target. Startup delivers `1.2` for `1.5` seconds, creating shortfall `(1.5-1.2)*1.5=0.45`; weighted by `10`, that contributes the extra `4.5`. Recovery duration, intervention, and P2 usage are unchanged. The evaluator enumerates off/off, off/on, on/off, and on/on. They alter the pre-isolation tank trajectory but have equal observed `J=13.375` here because this `J` contains no P1-flow or tank-level term. Their maximum is an exhaustive deterministic simulator diagnostic over these four schedules, **not** a formally proved hybrid-game cost bound.
