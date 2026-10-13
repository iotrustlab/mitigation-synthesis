#!/usr/bin/env bash
set -euo pipefail

# Slurm owns the lifetime of this process.  Keeping the batch shell alive lets
# independent, foreground `srun --jobid ...` steps use the reserved resources.
stop=0
trap 'stop=1' INT TERM HUP

while [ "${stop}" -eq 0 ]; do
    sleep 60 &
    wait "$!" || true
done
