# Parameterized Offline Recovery Certificate

This document describes the versioned symbolic theorem in
`parameterized_recovery_takeover.envelope`. It is separate from both the
canonical Phase-1 artifact and the concrete `timed_recovery_takeover.envelope`.

## Theorem

The theorem covers the fixed trusted-backup-takeover policy for every initial
state satisfying:

```text
L1 < H1, L2 < H2, L1 >= 0, L2 >= 0
L1 <= x1 <= H1, L2 <= x2 <= H2
qprimary >= 0, qbackup >= qmin > 0
0 < StartupDelay <= RecoveryDeadline, T > 0
isolationCost >= 0, backupCost >= 0
interventionBudget >= isolationCost + backupCost
```

The trusted policy immediately isolates P1, holds `qin=qd=0` for exactly
`StartupDelay`, activates P2, sets `qin=qd=qbackup`, and runs exactly one
positive operating interval `T`. P1 remains attacker-controlled before and
after isolation. The safety region is the whole closed rectangular tank region,
not merely the previous point `(7,6)`: both modeled phases have zero net tank
flow under the policy, so every safe initial level remains unchanged.

The postcondition requires safety, independent isolation, P2 activation,
effective-flow consistency, actual delivery `qdelivered=q2=qd >= qmin`, recovery
by `RecoveryDeadline`, one completed operating interval, and a nonnegative
remaining budget.

## Certificate Meaning

`COVERED_BY_CERTIFICATE` means that the supplied, validated runtime context has
the proved plant and policy identities and satisfies every theorem assumption.
It authorizes only this fixed synthetic takeover policy under this theorem. It
does not prove a deployment fact, discover a policy, command an actuator, or
show that a non-covered context is unsafe or globally infeasible.

Some facts are checked from runtime data: current tank levels, capacity/service,
timing, flow balance, budget, and context resources. Other facts are trusted
environment/configuration assumptions: the model and policy identities, the
independence and effectiveness of the isolator, the correctness of trusted
actuator/resource declarations, and the meaning of the synthetic plant model.

## Provenance Boundary

`parameterized_certificate_manifest.json` binds the certificate to hashes of the
symbolic envelope, renderer, and proof profile. `certificate.py` contains the
reviewed manifest digest and rejects altered, absent, or alternate manifests and
artifact mismatches. This detects local drift but does not independently rerun
or validate the KeYmaera X proof at runtime; the reviewed manifest and recorded
offline `VERIFIED` proof are the explicit trust boundary.

## Run

```bash
"$CLEO_PYTHON" -m recovery_experiment.verify_parameterized_recovery \
  --output-dir recovery_experiment/results/parameterized-formal

python3 -m recovery_experiment.certificate_evaluation --verify-concrete
```

The first command is the offline proof. The second command measures only context
validation, manifest/artifact checks, and numeric condition checks online; the
offline proof time is reported separately.
