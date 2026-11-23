# Attleboro ModelPlex generation receipt

On 2026-11-18, the KeYmaera X 5.0 JAR bundled with CLEO 0.1.0 parsed two single-entry copies of [remote_authority.kyx](../../attleboro/remote_authority.kyx) and generated controller monitor formulas with `-modelplex -monitor ctrl`. The [package README](../README.md) has portable rerun commands.

| Input | Generated formula | Original raw SHA-256 | Committed SHA-256 |
| --- | --- | --- | --- |
| `attleboro_bad_power_single_entry.kyx` | `attleboro_bad_power_ctrl.kym` | `fc8bbeaeb4aa9840e41198aa9974e4817d616690e7feeb3d0a80c5b22adee3da` | `48a2ca454ee13a15b2bcb8f84ca1af40a3b857dad544604d6bfd014e9a5f37a3` |
| `attleboro_restored_no_reset_single_entry.kyx` | `attleboro_restored_no_reset_ctrl.kym` | `08dc12d2c9bad39b01ab9896f1b9738c046fbae2341656ae3625ea2b9e272760` | `bf91467bff31c018a811bc9ce889110ec9d513e1b7365bb351c5bdcf17a02ab1` |

The first `@evidence` comment in each generated file originally included local absolute input and output paths. The committed copies change only those paths to basenames. The remainder of each file is byte-identical to the raw output (SHA-256 after the first newline: `cd80bea2d8bd8a0b5a97f3a58785fe47102f3da8abc65924b05bcdc117560006` for bad power and `7f63870e89722b26c972c1cd7cb92420d065f64869c4f387ac4d9c8d4fe8cb9a` for restored utility).

The successful legacy CLI form was:

```text
java -jar keymaerax.jar -launch -modelplex input.kyx \
  -monitor ctrl -out monitor.kym -tool z3 -timeout 60
```

These formulas describe discrete controller transitions. They do not monitor pump hydraulics, motor feedback, local Hand operation, network paths, or customer service. They also do not enforce each theorem's input antecedent; a runtime application would have to check its starting-state assumptions. No generated C monitor, deployment, or plant-monitor proof is claimed. The [trace receipt](TRACE_MONITOR_RECEIPT.md) records bounded offline evaluation.
