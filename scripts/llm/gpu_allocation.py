#!/usr/bin/env python3
"""Ownership-safe Slurm GPU allocation tooling for Dr.ICS.

The shell entry points in this directory deliberately delegate state parsing
and Slurm JSON handling to this dependency-free module.  The only operation
that decides GPU suitability is an nvidia-smi query made inside the allocation.
"""

from __future__ import print_function

import argparse
import csv
import datetime
import fcntl
import getpass
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import time


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_PARTITIONS = "soc-gpu-np:soc-gpu-np,notchpeak-gpu:notchpeak-gpu"
STATE_SCHEMA_VERSION = 1
TERMINAL_STATES = {
    "BOOT_FAIL",
    "CANCELLED",
    "COMPLETED",
    "DEADLINE",
    "FAILED",
    "NODE_FAIL",
    "OUT_OF_MEMORY",
    "PREEMPTED",
    "REVOKED",
    "TIMEOUT",
}
ENV_KEYS = (
    ("JOB_ID", "job_id"),
    ("NODE", "node"),
    ("PARTITION", "partition"),
    ("ACCOUNT", "account"),
    ("GPU_COUNT", "gpu_count"),
    ("GPU_NAME", "gpu_name"),
    ("GPU_MEMORY_MIB", "gpu_memory_mib"),
    ("GPU_UUIDS", "gpu_uuids"),
    ("WALLTIME", "walltime"),
    ("MINIMUM_VRAM_GIB", "minimum_vram_gib"),
    ("CREATED_AT", "created_at"),
    ("MANAGED_MARKER", "managed_marker"),
)


class AllocationError(RuntimeError):
    pass


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def runtime_dir():
    configured = os.environ.get("DRICS_GPU_STATE_DIR")
    return Path(configured).expanduser().resolve() if configured else REPO_ROOT / ".run" / "drics-gpu"


def owner_uid():
    return os.getuid()


def managed_marker(uid=None):
    uid = owner_uid() if uid is None else int(uid)
    repository_id = hashlib.sha256(str(REPO_ROOT.resolve()).encode("utf-8")).hexdigest()[:12]
    return "drics-gpu-v1:{}:{}".format(uid, repository_id)


def run_command(arguments, timeout=30, check=False, env=None):
    try:
        completed = subprocess.run(
            [str(item) for item in arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        if check:
            raise AllocationError("command failed: {}: {}".format(arguments[0], exc))
        return None
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "exit {}".format(
            completed.returncode
        )
        raise AllocationError("{} failed: {}".format(arguments[0], detail))
    return completed


def parse_freegpus(text):
    """Return (total_count, {model: count}) from advisory freegpus output."""
    models = {}
    pattern = re.compile(r"^\s*(.*?)\s+\(x([0-9]+)\)\s*$")
    for line in text.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        model = match.group(1).strip()
        if not model:
            continue
        models[model] = models.get(model, 0) + int(match.group(2))
    return sum(models.values()), models


def parse_gpu_csv(text):
    """Parse nvidia-smi CSV in either name,memory,uuid or indexed form."""
    result = []
    for row_number, row in enumerate(csv.reader(io.StringIO(text)), 1):
        if not row or all(not field.strip() for field in row):
            continue
        fields = [field.strip() for field in row]
        index = None
        if len(fields) == 3:
            name, memory, uuid = fields
        elif len(fields) == 4 and re.match(r"^[0-9]+$", fields[0]):
            index = int(fields[0])
            uuid, name, memory = fields[1:]
        else:
            raise ValueError("unexpected GPU CSV row {}: {!r}".format(row_number, row))
        if not re.match(r"^[0-9]+$", memory):
            raise ValueError("invalid GPU memory in row {}: {!r}".format(row_number, memory))
        item = {"name": name, "memory_mib": int(memory), "uuid": uuid}
        if index is not None:
            item["index"] = index
        result.append(item)
    return result


def vram_suitable(gpus, count, min_gib):
    count = int(count)
    threshold = int(min_gib) * 1024
    if count < 1 or len(gpus) < count:
        return False
    return all(int(gpu.get("memory_mib", -1)) >= threshold for gpu in gpus[:count])


def normalize_job_state(value):
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("name") or value.get("state")
    if not value:
        return "UNKNOWN"
    return str(value).strip().upper().split("+")[0]


def _state_env_value(value):
    if isinstance(value, (list, tuple)):
        return ",".join(str(item) for item in value)
    return str(value)


def serialize_state_env(state):
    lines = ["# Generated by scripts/llm/allocate_gpu.sh; do not edit."]
    for env_name, state_name in ENV_KEYS:
        value = state.get(state_name, "")
        lines.append("{}={}".format(env_name, shlex.quote(_state_env_value(value))))
    return "\n".join(lines) + "\n"


def _atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".{}-".format(path.name), suffix=".tmp", dir=str(path.parent))
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, str(path))
    except BaseException:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def write_state(state, json_path, env_path):
    _atomic_write(json_path, json.dumps(state, indent=2, sort_keys=True) + "\n")
    _atomic_write(env_path, serialize_state_env(state))


def read_state(json_path):
    with Path(json_path).open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    if not isinstance(state, dict):
        raise AllocationError("allocation state must be a JSON object")
    return state


def write_current_state(state):
    directory = runtime_dir()
    write_state(state, directory / "current.json", directory / "current.env")


def remove_current_state(expected_job_id=None):
    directory = runtime_dir()
    json_path = directory / "current.json"
    if expected_job_id is not None and json_path.exists():
        try:
            existing = read_state(json_path)
        except (OSError, ValueError, AllocationError):
            return False
        if int(existing.get("job_id", -1)) != int(expected_job_id):
            return False
    removed = False
    for path in (json_path, directory / "current.env"):
        try:
            path.unlink()
            removed = True
        except FileNotFoundError:
            pass
    return removed


def record_path(job_id):
    return runtime_dir() / "jobs" / "{}.json".format(int(job_id))


def write_job_record(record):
    path = record_path(record["job_id"])
    _atomic_write(path, json.dumps(record, indent=2, sort_keys=True) + "\n")


def choose_reusable_job(jobs, uid, name, marker):
    matches = []
    for job in jobs:
        if (
            int(job.get("user_id", -1)) == int(uid)
            and job.get("name") == name
            and job.get("comment") == marker
            and normalize_job_state(job.get("job_state")) == "RUNNING"
        ):
            matches.append(job)
    return sorted(matches, key=lambda item: int(item.get("job_id", 0)))[0] if matches else None


def should_cancel_job(job, uid, marker, submitted_ids, state_job_id):
    try:
        job_id = int(job.get("job_id"))
        owned = int(job.get("user_id", -1)) == int(uid)
    except (TypeError, ValueError):
        return False
    managed = owned and job.get("comment") == marker
    authorized = job_id in set(int(value) for value in submitted_ids)
    if state_job_id is not None:
        authorized = authorized or job_id == int(state_job_id)
    return managed and authorized


def _load_json_output(completed, description):
    if completed is None or completed.returncode != 0:
        detail = "command unavailable" if completed is None else completed.stderr.strip()
        raise AllocationError("could not query {}: {}".format(description, detail or "unknown error"))
    try:
        return json.loads(completed.stdout)
    except ValueError as exc:
        raise AllocationError("{} returned invalid JSON: {}".format(description, exc))


def query_jobs():
    payload = _load_json_output(run_command(["squeue", "--me", "--json"]), "Slurm queue")
    jobs = payload.get("jobs", [])
    return jobs if isinstance(jobs, list) else []


def query_job(job_id):
    completed = run_command(["scontrol", "--json", "show", "job", str(int(job_id))])
    if completed is None:
        raise AllocationError("could not query Slurm job {}: scontrol unavailable".format(job_id))
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        normalized = detail.lower()
        if "invalid job id" in normalized or "not found" in normalized:
            return None
        raise AllocationError("could not query Slurm job {}: {}".format(job_id, detail or "unknown error"))
    try:
        jobs = json.loads(completed.stdout).get("jobs", [])
    except (ValueError, AttributeError) as exc:
        raise AllocationError("Slurm returned invalid JSON for job {}: {}".format(job_id, exc))
    if not isinstance(jobs, list):
        raise AllocationError("Slurm returned an invalid jobs collection for job {}".format(job_id))
    return jobs[0] if jobs else None


def job_owned_and_managed(job, uid, marker):
    if not job:
        return False
    try:
        same_owner = int(job.get("user_id", -1)) == int(uid)
    except (TypeError, ValueError):
        return False
    return same_owner and job.get("comment") == marker


def parse_partitions(value):
    pairs = []
    seen = set()
    for token in re.split(r"[\s,]+", value.strip()):
        if not token:
            continue
        pieces = token.split(":")
        if len(pieces) != 2 or not all(re.match(r"^[A-Za-z0-9_.-]+$", item) for item in pieces):
            raise AllocationError(
                "invalid partition/account pair {!r}; expected PARTITION:ACCOUNT".format(token)
            )
        pair = (pieces[0], pieces[1])
        if pair not in seen:
            pairs.append(pair)
            seen.add(pair)
    if not pairs:
        raise AllocationError("DRICS_GPU_PARTITIONS did not contain any partition/account pairs")
    return pairs


def advertised_gpu_types(partition):
    completed = run_command(["sinfo", "-p", partition, "-N", "-h", "-o", "%G"])
    if completed is None or completed.returncode != 0:
        return set()
    result = set()
    for line in completed.stdout.splitlines():
        for gres in line.split(","):
            match = re.search(r"(?:^|/)gpu:([^:,()]+):[0-9]+", gres.strip())
            if match:
                result.add(match.group(1))
    return result


def inspect_partition(partition):
    completed = run_command(["scontrol", "--json", "show", "partition", partition])
    if completed is None or completed.returncode != 0:
        return None
    try:
        parts = json.loads(completed.stdout).get("partitions", [])
        return parts[0] if parts else None
    except (ValueError, AttributeError):
        return None


def freegpu_report(partition):
    completed = run_command(["freegpus", "-p", partition])
    if completed is None:
        return {"ok": False, "text": "freegpus command unavailable", "count": None, "models": {}}
    text = completed.stdout.strip()
    if completed.stderr.strip():
        text = (text + "\n" + completed.stderr.strip()).strip()
    if completed.returncode != 0:
        return {"ok": False, "text": text, "count": None, "models": {}}
    count, models = parse_freegpus(text)
    return {"ok": True, "text": text, "count": count, "models": models}


def _print_discovery(partition, account, report, gpu_types):
    print("Partition: {}".format(partition))
    print("Account: {}".format(account))
    print("Advertised GPU types: {}".format(", ".join(sorted(gpu_types)) or "not available"))
    print("freegpus output (advisory):")
    if report["text"]:
        for line in report["text"].splitlines():
            print("  {}".format(line))
    else:
        print("  (no output)")
    count_text = "unknown" if report["count"] is None else str(report["count"])
    print("Total free GPU count (advisory): {}".format(count_text))


def partition_allows_account(partition_info, account):
    if not partition_info:
        return False
    accounts = partition_info.get("accounts", {})
    allowed = accounts.get("allowed", "") if isinstance(accounts, dict) else ""
    if not allowed or str(allowed).upper() == "ALL":
        return True
    tokens = set(re.split(r"[,\s]+", str(allowed).strip()))
    return account in tokens


def _visible_gpu_subset(gpus, visible_value):
    if not visible_value or visible_value.strip().lower() in ("all", "void", "none"):
        return gpus
    selected = []
    tokens = [token.strip() for token in visible_value.split(",") if token.strip()]
    for token in tokens:
        match = None
        for gpu in gpus:
            uuid = str(gpu.get("uuid", ""))
            if token == str(gpu.get("index", "")) or token == uuid or uuid.startswith(token):
                match = gpu
                break
        if match is None:
            raise AllocationError("visible GPU token {!r} did not match nvidia-smi output".format(token))
        if match not in selected:
            selected.append(match)
    return selected


def internal_inspect():
    completed = run_command(
        [
            "nvidia-smi",
            "--query-gpu=index,uuid,name,memory.total",
            "--format=csv,noheader,nounits",
        ],
        timeout=30,
    )
    if completed is None or completed.returncode != 0:
        detail = "nvidia-smi unavailable" if completed is None else completed.stderr.strip()
        print(json.dumps({"ok": False, "error": detail or "nvidia-smi failed"}, sort_keys=True))
        return 1
    try:
        all_gpus = parse_gpu_csv(completed.stdout)
        visible = (
            os.environ.get("CUDA_VISIBLE_DEVICES")
            or os.environ.get("NVIDIA_VISIBLE_DEVICES")
            or os.environ.get("SLURM_JOB_GPUS")
            or ""
        )
        selected = _visible_gpu_subset(all_gpus, visible)
    except (ValueError, AllocationError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    payload = {
        "ok": True,
        "hostname": os.uname().nodename.split(".")[0],
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES", ""),
        "slurm_job_gpus": os.environ.get("SLURM_JOB_GPUS", ""),
        "gpus": selected,
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


def inspect_allocated_gpu(job_id, node):
    python = os.environ.get("DRICS_PYTHON") or str(REPO_ROOT / ".venv" / "bin" / "python")
    if not os.path.isfile(python):
        python = sys.executable
    command = [
        "srun",
        "--jobid={}".format(int(job_id)),
        "--nodes=1",
        "--ntasks=1",
        "--nodelist={}".format(node),
        "--overlap",
        "--quiet",
        python,
        str(Path(__file__).resolve()),
        "_inspect",
    ]
    completed = run_command(command, timeout=90)
    if completed is None or completed.returncode != 0:
        detail = "srun unavailable" if completed is None else (completed.stderr.strip() or completed.stdout.strip())
        raise AllocationError("in-allocation GPU inspection failed: {}".format(detail or "unknown error"))
    for line in reversed(completed.stdout.splitlines()):
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        if isinstance(payload, dict) and "ok" in payload:
            if not payload.get("ok"):
                raise AllocationError(payload.get("error", "GPU inspection failed"))
            return payload
    raise AllocationError("in-allocation GPU inspection returned no JSON result")


def _job_node(job):
    value = job.get("nodes") or job.get("node_list") or ""
    if isinstance(value, list):
        value = value[0] if value else ""
    value = str(value)
    if not value or "[" in value or "," in value:
        return ""
    return value.split(".")[0]


def state_from_job(job, inspection, arguments, marker, created_at=None):
    selected = inspection["gpus"][: arguments.gpus]
    memories = [int(gpu["memory_mib"]) for gpu in selected]
    names = [gpu["name"] for gpu in selected]
    uuids = [gpu["uuid"] for gpu in selected]
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "managed_marker": marker,
        "job_id": int(job["job_id"]),
        "job_name": job.get("name") or arguments.job_name,
        "owner": getpass.getuser(),
        "owner_uid": owner_uid(),
        "node": inspection.get("hostname") or _job_node(job),
        "partition": job.get("partition") or getattr(arguments, "partition", ""),
        "account": job.get("account") or getattr(arguments, "account", ""),
        "cpus": arguments.cpus,
        "host_memory": arguments.mem,
        "gpu_count": arguments.gpus,
        "gpu_name": "; ".join(names),
        "gpu_names": names,
        "gpu_memory_mib": min(memories),
        "gpu_memory_mib_all": memories,
        "gpu_uuids": uuids,
        "cuda_visible_devices": inspection.get("cuda_visible_devices", ""),
        "slurm_job_gpus": inspection.get("slurm_job_gpus", ""),
        "minimum_vram_gib": arguments.min_vram,
        "walltime": arguments.walltime,
        "created_at": created_at or utc_now(),
        "validated_at": utc_now(),
    }


def _print_ready(state, reused=False):
    if reused:
        print("Reusing existing Dr.ICS GPU allocation")
    print("Job ID: {}".format(state["job_id"]))
    print("Node: {}".format(state["node"]))
    print("Partition: {}".format(state["partition"]))
    print("GPU: {}".format(state["gpu_name"]))
    print("VRAM: {:.2f} GiB ({} MiB minimum across selected GPUs)".format(
        state["gpu_memory_mib"] / 1024.0, state["gpu_memory_mib"]
    ))
    print("Walltime: {}".format(state["walltime"]))
    print("Release: scripts/llm/release_gpu.sh --job-id {}".format(state["job_id"]))
    print("DRICS_GPU_READY=1")
    print("DRICS_GPU_JOB_ID={}".format(state["job_id"]))
    print("DRICS_GPU_NODE={}".format(state["node"]))
    print("DRICS_GPU_PARTITION={}".format(state["partition"]))
    print("DRICS_GPU_NAME={}".format(re.sub(r"\s+", "_", state["gpu_name"])))
    print("DRICS_GPU_MEMORY_MIB={}".format(state["gpu_memory_mib"]))
    print("DRICS_GPU_STATE_FILE={}".format(runtime_dir() / "current.env"))


def _print_not_ready(reason, job_id=None):
    print("DRICS_GPU_READY=0")
    if job_id is not None:
        print("DRICS_GPU_JOB_ID={}".format(job_id))
    print("DRICS_GPU_REASON={}".format(reason))


def _validate_positive(value, label):
    try:
        integer = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("{} must be an integer".format(label))
    if integer < 1:
        raise argparse.ArgumentTypeError("{} must be at least 1".format(label))
    return integer


def _parse_gpu_type(value, count):
    if not value:
        return None, "gpu:{}".format(count)
    if re.match(r"^[A-Za-z0-9_.-]+$", value):
        return value, "gpu:{}:{}".format(value, count)
    match = re.match(r"^gpu:([A-Za-z0-9_.-]+):([0-9]+)$", value)
    if not match:
        raise AllocationError("--gpu-type/DRICS_GPU_GRES must be TYPE or gpu:TYPE:COUNT")
    if int(match.group(2)) != count:
        raise AllocationError("DRICS_GPU_GRES count does not match --gpus")
    return match.group(1), value


def _slurm_numeric(field):
    if isinstance(field, dict):
        if field.get("infinite"):
            return float("inf")
        field = field.get("number")
    try:
        return int(field)
    except (TypeError, ValueError):
        return None


def memory_to_mib(value):
    match = re.match(r"^([0-9]+)([KMGTP]?)$", str(value).strip(), re.IGNORECASE)
    if not match:
        raise AllocationError("cannot parse Slurm memory request {!r}".format(value))
    amount = int(match.group(1))
    unit = match.group(2).upper()
    factors = {"": 1, "K": 1.0 / 1024.0, "M": 1, "G": 1024, "T": 1024 ** 2, "P": 1024 ** 3}
    return int(amount * factors[unit])


def walltime_to_minutes(value):
    match = re.match(r"^(?:([0-9]+)-)?([0-9]+):([0-9]{2}):([0-9]{2})$", str(value))
    if not match:
        raise AllocationError("cannot parse walltime {!r}".format(value))
    days = int(match.group(1) or 0)
    hours, minutes, seconds = (int(item) for item in match.groups()[1:])
    return days * 24 * 60 + hours * 60 + minutes + (1 if seconds else 0)


def job_resource_problem(job, arguments, gpu_type=None):
    allocated_cpus = _slurm_numeric(job.get("cpus"))
    if allocated_cpus is None or allocated_cpus < arguments.cpus:
        return "job has {} CPUs; {} requested".format(allocated_cpus, arguments.cpus)
    memory_mib = _slurm_numeric(job.get("memory_per_node"))
    if memory_mib is None:
        per_cpu = _slurm_numeric(job.get("memory_per_cpu"))
        memory_mib = None if per_cpu is None else per_cpu * allocated_cpus
    requested_memory_mib = memory_to_mib(arguments.mem)
    if memory_mib is None or memory_mib < requested_memory_mib:
        return "job has {} MiB host RAM; {} MiB requested".format(memory_mib, requested_memory_mib)
    allocated_minutes = _slurm_numeric(job.get("time_limit"))
    requested_minutes = walltime_to_minutes(arguments.walltime)
    if allocated_minutes is None or allocated_minutes < requested_minutes:
        return "job time limit is {} minutes; {} requested".format(allocated_minutes, requested_minutes)
    end = job.get("end_time")
    end_epoch = _slurm_numeric(end)
    try:
        minimum_remaining = int(os.environ.get("DRICS_GPU_MIN_REMAINING_SECONDS", "900"))
    except ValueError:
        raise AllocationError("DRICS_GPU_MIN_REMAINING_SECONDS must be an integer")
    if minimum_remaining < 0:
        raise AllocationError("DRICS_GPU_MIN_REMAINING_SECONDS cannot be negative")
    if end_epoch is not None and end_epoch != float("inf") and end_epoch - time.time() < minimum_remaining:
        return "job has less than {} seconds remaining".format(minimum_remaining)
    if gpu_type:
        gres_detail = job.get("gres_detail") or []
        if isinstance(gres_detail, str):
            gres_detail = [gres_detail]
        pattern = re.compile(r"(?:^|,)gpu:{}:([0-9]+)".format(re.escape(gpu_type)))
        typed_count = 0
        for detail in gres_detail:
            typed_count += sum(int(match.group(1)) for match in pattern.finditer(str(detail)))
        if typed_count < arguments.gpus:
            return "job does not prove {} allocated GPU(s) of type {!r}".format(arguments.gpus, gpu_type)
    return None


def _job_reason(job):
    value = job.get("state_reason") or job.get("state_description") or "unspecified"
    if isinstance(value, dict):
        value = value.get("name") or value.get("description") or str(value)
    return str(value)


def wait_for_job(job_id, wait_seconds, poll_seconds, newly_submitted):
    deadline = time.monotonic() + wait_seconds
    last_message = None
    while True:
        job = query_job(job_id)
        if job is None:
            raise AllocationError("Slurm job {} disappeared".format(job_id))
        state = normalize_job_state(job.get("job_state"))
        reason = _job_reason(job)
        message = "Allocation {}: {} (reason: {}, partition: {})".format(
            job_id, state, reason, job.get("partition", "unknown")
        )
        if message != last_message:
            print(message)
            last_message = message
        if state == "RUNNING":
            return job
        if state in TERMINAL_STATES:
            raise AllocationError("Slurm job {} entered {} ({})".format(job_id, state, reason))
        if not newly_submitted and wait_seconds == 0:
            return job
        if time.monotonic() >= deadline:
            raise AllocationError("allocation wait timeout after {} seconds".format(wait_seconds))
        time.sleep(poll_seconds)


def _cancel_verified(job_id, marker, submitted_ids, state_job_id=None):
    job = query_job(job_id)
    if job is None or normalize_job_state(job.get("job_state")) in TERMINAL_STATES:
        return True
    if not should_cancel_job(job, owner_uid(), marker, submitted_ids, state_job_id):
        raise AllocationError("refusing to cancel job {}: ownership/managed-state check failed".format(job_id))
    completed = run_command(["scancel", str(int(job_id))], timeout=30)
    if completed is None or completed.returncode != 0:
        detail = "scancel unavailable" if completed is None else completed.stderr.strip()
        raise AllocationError("could not cancel managed job {}: {}".format(job_id, detail or "unknown error"))
    for _ in range(20):
        current = query_job(job_id)
        if current is None or normalize_job_state(current.get("job_state")) in TERMINAL_STATES:
            return True
        time.sleep(0.5)
    raise AllocationError("job {} did not reach a terminal state after scancel".format(job_id))


def _find_managed_named_jobs(jobs, uid, name, marker):
    result = []
    for job in jobs:
        try:
            owner_matches = int(job.get("user_id", -1)) == int(uid)
        except (TypeError, ValueError):
            owner_matches = False
        if owner_matches and job.get("name") == name and job.get("comment") == marker:
            result.append(job)
    priority = {"RUNNING": 0, "CONFIGURING": 1, "PENDING": 2}
    return sorted(
        result,
        key=lambda job: (priority.get(normalize_job_state(job.get("job_state")), 9), int(job.get("job_id", 0))),
    )


def _validate_and_accept(job, arguments, marker, reused, created_at=None, persist=True, gpu_type=None):
    resource_problem = job_resource_problem(job, arguments, gpu_type=gpu_type)
    if resource_problem:
        raise AllocationError("allocation resources are insufficient: {}".format(resource_problem))
    node = _job_node(job)
    if not node:
        raise AllocationError("running job {} has no single allocated node".format(job.get("job_id")))
    inspection = inspect_allocated_gpu(job["job_id"], node)
    gpus = inspection.get("gpus", [])
    if not vram_suitable(gpus, arguments.gpus, arguments.min_vram):
        memories = ",".join(str(gpu.get("memory_mib", "?")) for gpu in gpus) or "none"
        raise AllocationError(
            "allocated GPU is insufficient: requested {} GPU(s) with at least {} GiB each; observed {} GPU(s), memory MiB [{}]".format(
                arguments.gpus, arguments.min_vram, len(gpus), memories
            )
        )
    state = state_from_job(job, inspection, arguments, marker, created_at=created_at)
    if persist:
        record = dict(state)
        record["status"] = "ACCEPTED"
        try:
            write_job_record(record)
            write_current_state(state)
        except OSError as exc:
            raise AllocationError("could not persist accepted allocation state: {}".format(exc))
    _print_ready(state, reused=reused)
    return state


def _validate_allocate_args(arguments):
    if not re.match(r"^[A-Za-z0-9_.-]+$", arguments.job_name):
        raise AllocationError("--job-name contains unsupported characters")
    if not re.match(r"^(?:[0-9]+-)?[0-9]+:[0-9]{2}:[0-9]{2}$", arguments.walltime):
        raise AllocationError("--walltime must use HH:MM:SS or D-HH:MM:SS")
    if not re.match(r"^[0-9]+(?:[KMGTP])?$", arguments.mem, re.IGNORECASE):
        raise AllocationError("--mem must be a Slurm memory value such as 32G")
    if arguments.poll_seconds <= 0:
        raise AllocationError("--poll-seconds must be greater than zero")
    if arguments.wait_seconds < 0:
        raise AllocationError("--wait-seconds cannot be negative")


def allocate(arguments):
    _validate_allocate_args(arguments)
    partitions = parse_partitions(arguments.partitions)
    gpu_type, gres = _parse_gpu_type(arguments.gpu_type, arguments.gpus)
    marker = managed_marker()
    directory = runtime_dir()
    lock_handle = None
    if not arguments.dry_run:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "logs").mkdir(parents=True, exist_ok=True)
        (directory / "jobs").mkdir(parents=True, exist_ok=True)
        lock_path = directory / "allocator.lock"
        lock_handle = lock_path.open("a+")
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            lock_handle.close()
            _print_not_ready("ALLOCATOR_BUSY")
            return 3

    reports = []
    submitted_ids = set()
    active_submitted_job_id = None
    previous_signal_handlers = {}

    def interrupt_allocation(signum, frame):
        del signum, frame
        raise KeyboardInterrupt()

    for signal_number in (signal.SIGTERM, signal.SIGHUP):
        previous_signal_handlers[signal_number] = signal.getsignal(signal_number)
        signal.signal(signal_number, interrupt_allocation)
    try:
        print("GPU suitability policy: {} GPU(s), {} GiB minimum VRAM per GPU".format(
            arguments.gpus, arguments.min_vram
        ))
        print("freegpus is advisory; nvidia-smi inside a RUNNING allocation is authoritative.")
        for partition, account in partitions:
            report = freegpu_report(partition)
            gpu_types = advertised_gpu_types(partition)
            partition_info = inspect_partition(partition)
            _print_discovery(partition, account, report, gpu_types)
            if partition_info is None:
                print("Partition status: unavailable from Slurm; skipping")
            else:
                allowed = partition_info.get("accounts", {}).get("allowed", "unknown")
                print("Partition discovered by Slurm; allowed accounts: {}".format(allowed))
                if not partition_allows_account(partition_info, account):
                    print("Configured account {} is not allowed by this partition.".format(account))
            reports.append((partition, account, report, gpu_types, partition_info))

        if arguments.dry_run:
            for partition, account, report, gpu_types, partition_info in reports:
                if partition_info is None or not partition_allows_account(partition_info, account):
                    continue
                if report["count"] is not None and report["count"] < arguments.gpus:
                    print("DRY RUN skip {}: advisory free count is below request.".format(partition))
                    continue
                if gpu_type and gpu_types and gpu_type not in gpu_types:
                    print("DRY RUN skip {}: GPU type {!r} is not advertised.".format(partition, gpu_type))
                    continue
                if gpu_type and report["models"] and report["models"].get(gpu_type, 0) < arguments.gpus:
                    print("DRY RUN skip {}: freegpus does not report enough {!r} GPUs.".format(partition, gpu_type))
                    continue
                log_pattern = directory / "logs" / "{}-%j.out".format(arguments.job_name)
                command = [
                    "sbatch", "--parsable", "--nodes=1", "--ntasks=1",
                    "--cpus-per-task={}".format(arguments.cpus), "--mem={}".format(arguments.mem),
                    "--time={}".format(arguments.walltime), "--gres={}".format(gres),
                    "--partition={}".format(partition), "--account={}".format(account),
                    "--job-name={}".format(arguments.job_name), "--comment={}".format(marker),
                    "--output={}".format(log_pattern), str(SCRIPT_DIR / "hold_gpu_allocation.sh"),
                ]
                print("DRY RUN submission: {}".format(" ".join(shlex.quote(item) for item in command)))
            _print_not_ready("DRY_RUN")
            return 0

        jobs = query_jobs()
        owned_active = []
        for job in jobs:
            try:
                is_owner = int(job.get("user_id", -1)) == owner_uid()
            except (TypeError, ValueError):
                is_owner = False
            if is_owner:
                owned_active.append(job)
        collisions = [
            job for job in owned_active
            if job.get("name") == arguments.job_name and job.get("comment") != marker
        ]
        if collisions:
            collision_ids = ",".join(str(job.get("job_id")) for job in collisions)
            print(
                "Refusing to submit beside owned same-name job(s) {} without this repository's managed marker."
                .format(collision_ids),
                file=sys.stderr,
            )
            _print_not_ready("UNMANAGED_JOB_NAME_COLLISION")
            return 2
        managed_jobs = _find_managed_named_jobs(jobs, owner_uid(), arguments.job_name, marker)
        other_managed_jobs = [
            job for job in owned_active
            if job.get("comment") == marker and job.get("name") != arguments.job_name
        ]
        if other_managed_jobs:
            description = ",".join(
                "{}:{}".format(job.get("job_id"), job.get("name")) for job in other_managed_jobs
            )
            print(
                "Existing repository-managed allocation(s) use a different job name: {}. No duplicate was submitted."
                .format(description),
                file=sys.stderr,
            )
            _print_not_ready("EXISTING_MANAGED_ALLOCATION_DIFFERENT_NAME")
            return 2
        if len(managed_jobs) > 1:
            description = ",".join(str(job.get("job_id")) for job in managed_jobs)
            print(
                "Multiple active repository-managed jobs match this name ({}); refusing ambiguous reuse."
                .format(description),
                file=sys.stderr,
            )
            _print_not_ready("MULTIPLE_MANAGED_ALLOCATIONS")
            return 2
        if managed_jobs:
            existing = managed_jobs[0]
            state = normalize_job_state(existing.get("job_state"))
            job_id = int(existing["job_id"])
            if state != "RUNNING":
                if not arguments.wait:
                    print("Existing managed allocation {} is {}.".format(job_id, state))
                    _print_not_ready("ALLOCATION_PENDING", job_id)
                    return 2
                try:
                    existing = wait_for_job(job_id, arguments.wait_seconds, arguments.poll_seconds, False)
                except AllocationError as exc:
                    print("Existing managed allocation was not changed: {}".format(exc), file=sys.stderr)
                    _print_not_ready("EXISTING_ALLOCATION_NOT_READY", job_id)
                    return 2
            try:
                _validate_and_accept(existing, arguments, marker, reused=True, gpu_type=gpu_type)
                return 0
            except AllocationError as exc:
                print("Existing managed allocation was not changed: {}".format(exc), file=sys.stderr)
                _print_not_ready("EXISTING_ALLOCATION_INSUFFICIENT", job_id)
                return 2

        attempted = 0
        for partition, account, report, gpu_types, partition_info in reports:
            if partition_info is None or not partition_allows_account(partition_info, account):
                continue
            if report["count"] is not None and report["count"] < arguments.gpus:
                print("Skipping {}: advisory free count {} is below requested {}.".format(
                    partition, report["count"], arguments.gpus
                ))
                continue
            if gpu_type and gpu_types and gpu_type not in gpu_types:
                print("Skipping {}: GPU type {!r} is not advertised there.".format(partition, gpu_type))
                continue
            if gpu_type and report["models"] and report["models"].get(gpu_type, 0) < arguments.gpus:
                print("Skipping {}: freegpus reports no available {!r} request.".format(partition, gpu_type))
                continue
            attempted += 1
            log_pattern = directory / "logs" / "{}-%j.out".format(arguments.job_name)
            command = [
                "sbatch", "--parsable", "--nodes=1", "--ntasks=1",
                "--cpus-per-task={}".format(arguments.cpus), "--mem={}".format(arguments.mem),
                "--time={}".format(arguments.walltime), "--gres={}".format(gres),
                "--partition={}".format(partition), "--account={}".format(account),
                "--job-name={}".format(arguments.job_name), "--comment={}".format(marker),
                "--output={}".format(log_pattern), str(SCRIPT_DIR / "hold_gpu_allocation.sh"),
            ]
            completed = run_command(command, timeout=30)
            if completed is None or completed.returncode != 0:
                detail = "sbatch unavailable" if completed is None else completed.stderr.strip()
                print("Submission to {} failed: {}".format(partition, detail or "unknown error"), file=sys.stderr)
                continue
            job_id_matches = re.findall(r"(?m)^([0-9]+)(?:;[^\s]+)?\s*$", completed.stdout)
            if len(job_id_matches) != 1:
                raise AllocationError(
                    "sbatch succeeded but returned an invalid job ID {!r}; refusing another submission"
                    .format(completed.stdout.strip())
                )
            job_id = int(job_id_matches[0])
            submitted_ids.add(job_id)
            active_submitted_job_id = job_id
            record = {
                "schema_version": STATE_SCHEMA_VERSION, "managed_marker": marker,
                "job_id": job_id, "job_name": arguments.job_name, "owner": getpass.getuser(),
                "owner_uid": owner_uid(), "partition": partition, "account": account,
                "gpu_count": arguments.gpus, "minimum_vram_gib": arguments.min_vram,
                "walltime": arguments.walltime, "created_at": utc_now(), "status": "PENDING",
            }
            try:
                write_job_record(record)
            except OSError as exc:
                try:
                    _cancel_verified(job_id, marker, submitted_ids)
                except AllocationError as cleanup_error:
                    raise AllocationError(
                        "could not record submitted job {} ({}), and cleanup failed ({})"
                        .format(job_id, exc, cleanup_error)
                    )
                active_submitted_job_id = None
                raise AllocationError(
                    "could not record submitted job {}; it was cancelled: {}".format(job_id, exc)
                )
            print("Submitted managed Dr.ICS allocation {} to {}/{}.".format(job_id, partition, account))
            if not arguments.wait:
                active_submitted_job_id = None
                _print_not_ready("ALLOCATION_PENDING", job_id)
                return 2
            try:
                job = wait_for_job(job_id, arguments.wait_seconds, arguments.poll_seconds, True)
                arguments.partition = partition
                arguments.account = account
                _validate_and_accept(
                    job, arguments, marker, reused=False, created_at=record["created_at"], gpu_type=gpu_type
                )
                active_submitted_job_id = None
                return 0
            except (AllocationError, KeyboardInterrupt) as exc:
                label = "interrupted" if isinstance(exc, KeyboardInterrupt) else str(exc)
                print("Rejecting allocation {}: {}".format(job_id, label), file=sys.stderr)
                try:
                    _cancel_verified(job_id, marker, submitted_ids)
                    remove_current_state(job_id)
                    record["status"] = "CANCELLED_AFTER_REJECTION"
                    record["rejection_reason"] = label
                    record["updated_at"] = utc_now()
                    write_job_record(record)
                    active_submitted_job_id = None
                except AllocationError as cleanup_error:
                    print("ERROR: {}; refusing another submission.".format(cleanup_error), file=sys.stderr)
                    _print_not_ready("REJECTED_JOB_CLEANUP_FAILED", job_id)
                    return 3
                if isinstance(exc, KeyboardInterrupt):
                    _print_not_ready("INTERRUPTED")
                    return 130

        reason = "NO_SUITABLE_GPU_AVAILABLE"
        if attempted == 0:
            print("No candidate had sufficient advisory availability.")
        _print_not_ready(reason)
        return 2
    except KeyboardInterrupt:
        if active_submitted_job_id is not None:
            try:
                _cancel_verified(active_submitted_job_id, marker, submitted_ids)
                remove_current_state(active_submitted_job_id)
            except AllocationError as cleanup_error:
                print(
                    "ERROR: interrupted, but managed job {} cleanup failed: {}".format(
                        active_submitted_job_id, cleanup_error
                    ),
                    file=sys.stderr,
                )
                _print_not_ready("INTERRUPTED_CLEANUP_FAILED", active_submitted_job_id)
                return 3
        _print_not_ready("INTERRUPTED")
        return 130
    finally:
        for signal_number, previous_handler in previous_signal_handlers.items():
            signal.signal(signal_number, previous_handler)
        if lock_handle is not None:
            try:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            finally:
                lock_handle.close()


def _remaining_time(job):
    end = job.get("end_time")
    if isinstance(end, dict) and end.get("set") and isinstance(end.get("number"), (int, float)):
        remaining = max(0, int(end["number"] - time.time()))
        hours, remainder = divmod(remaining, 3600)
        minutes, seconds = divmod(remainder, 60)
        return "{:02d}:{:02d}:{:02d}".format(hours, minutes, seconds)
    return "unknown"


def status(arguments):
    path = runtime_dir() / "current.json"
    try:
        state = read_state(path)
    except (OSError, ValueError, AllocationError) as exc:
        print("Status: NOT_READY")
        print("Reason: no readable current allocation state ({})".format(exc))
        _print_not_ready("NO_CURRENT_ALLOCATION")
        return 1
    job_id = state.get("job_id")
    job = query_job(job_id)
    marker = managed_marker()
    if job is None:
        remove_current_state(job_id)
        print("Status: NOT_READY\nReason: recorded Slurm job no longer exists")
        _print_not_ready("STALE_STATE")
        return 1
    if not job_owned_and_managed(job, owner_uid(), marker) or state.get("managed_marker") != marker:
        print("Status: NOT_READY\nReason: ownership or managed marker mismatch")
        _print_not_ready("OWNERSHIP_MISMATCH")
        return 1
    job_state = normalize_job_state(job.get("job_state"))
    if job_state != "RUNNING":
        if job_state in TERMINAL_STATES:
            remove_current_state(job_id)
        print("Status: {}".format(job_state))
        print("Reason: {}".format(_job_reason(job)))
        _print_not_ready("JOB_NOT_RUNNING", job_id)
        return 1
    node = _job_node(job)
    if not arguments.no_recheck:
        try:
            inspection = inspect_allocated_gpu(job_id, node)
        except AllocationError as exc:
            print("Status: NOT_READY\nReason: {}".format(exc))
            _print_not_ready("GPU_RECHECK_FAILED", job_id)
            return 1
        if not vram_suitable(inspection.get("gpus", []), int(state["gpu_count"]), int(state["minimum_vram_gib"])):
            print("Status: NOT_READY\nReason: GPU no longer meets recorded suitability policy")
            _print_not_ready("GPU_INSUFFICIENT", job_id)
            return 1
    print("Status: READY")
    print("Job: {}".format(job_id))
    print("Node: {}".format(node))
    print("GPU: {}".format(state["gpu_name"]))
    print("VRAM: {} MiB".format(state["gpu_memory_mib"]))
    print("Remaining walltime: {}".format(_remaining_time(job)))
    _print_ready(state, reused=True)
    return 0


def release(arguments):
    directory = runtime_dir()
    current_path = directory / "current.json"
    current = None
    try:
        current = read_state(current_path)
    except (OSError, ValueError, AllocationError):
        pass
    job_id = arguments.job_id or (current.get("job_id") if current else None)
    if job_id is None:
        print("ERROR: no recorded Dr.ICS GPU allocation was found.", file=sys.stderr)
        return 1
    job_id = int(job_id)
    record_file = record_path(job_id)
    try:
        record = read_state(record_file)
    except (OSError, ValueError, AllocationError):
        print("ERROR: refusing job {}: no valid per-job Dr.ICS record exists.".format(job_id), file=sys.stderr)
        return 3
    marker = managed_marker()
    if int(record.get("job_id", -1)) != job_id or record.get("managed_marker") != marker or int(record.get("owner_uid", -1)) != owner_uid():
        print("ERROR: refusing job {}: the local record does not prove ownership.".format(job_id), file=sys.stderr)
        return 3
    job = query_job(job_id)
    if job is None or normalize_job_state(job.get("job_state")) in TERMINAL_STATES:
        remove_current_state(job_id)
        record["status"] = "ALREADY_FINISHED"
        record["updated_at"] = utc_now()
        write_job_record(record)
        print("Recorded Dr.ICS allocation {} is already absent or finished; stale current state removed.".format(job_id))
        return 0
    if not should_cancel_job(job, owner_uid(), marker, set(), job_id):
        print("ERROR: refusing to cancel job {}: Slurm ownership/marker mismatch.".format(job_id), file=sys.stderr)
        return 3
    try:
        _cancel_verified(job_id, marker, set(), state_job_id=job_id)
    except AllocationError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 3
    remove_current_state(job_id)
    record["status"] = "RELEASED"
    record["updated_at"] = utc_now()
    write_job_record(record)
    server_state_path = directory / "qwen-server.json"
    try:
        server_state = read_state(server_state_path)
        if int(server_state.get("job_id", -1)) == job_id:
            server_state_path.unlink()
    except (OSError, ValueError, AllocationError):
        pass
    print("Released recorded Dr.ICS GPU allocation {}.".format(job_id))
    return 0


def _remove_server_state(expected_token):
    path = runtime_dir() / "qwen-server.json"
    try:
        state = read_state(path)
    except (OSError, ValueError, AllocationError):
        return False
    if state.get("token") != expected_token:
        return False
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def stop_server(arguments):
    """Stop only the recorded Qwen Slurm step, never its allocation job."""
    path = runtime_dir() / "qwen-server.json"
    try:
        state = read_state(path)
    except (OSError, ValueError, AllocationError) as exc:
        print("ERROR: no readable Qwen server state: {}".format(exc), file=sys.stderr)
        return 1
    token = state.get("token")
    try:
        job_id = int(state["job_id"])
        step_id = str(state["step_id"])
        recorded_uid = int(state["owner_uid"])
    except (KeyError, TypeError, ValueError):
        print("ERROR: Qwen server state is incomplete.", file=sys.stderr)
        return 3
    if not token or not re.match(r"^[0-9]+$", step_id):
        print("ERROR: refusing a non-numeric, batch, or extern Slurm step.", file=sys.stderr)
        return 3
    marker = managed_marker()
    job = query_job(job_id)
    if job is None or normalize_job_state(job.get("job_state")) in TERMINAL_STATES:
        _remove_server_state(token)
        print("The recorded Qwen step is already gone; stale server state was removed.")
        return 0
    if (
        recorded_uid != owner_uid()
        or state.get("managed_marker") != marker
        or not job_owned_and_managed(job, owner_uid(), marker)
        or state.get("node") != _job_node(job)
    ):
        print("ERROR: refusing to stop server: allocation ownership/node check failed.", file=sys.stderr)
        return 3
    step_target = "{}.{}".format(job_id, step_id)
    exists = run_command(["scontrol", "show", "step", step_target], timeout=30)
    if exists is None:
        print("ERROR: could not query the recorded Qwen step.", file=sys.stderr)
        return 3
    if exists.returncode != 0:
        detail = (exists.stderr or exists.stdout).strip()
        normalized = detail.lower()
        if "invalid job" not in normalized and "not found" not in normalized:
            print("ERROR: could not verify Qwen step {}: {}".format(step_target, detail), file=sys.stderr)
            return 3
        _remove_server_state(token)
        print("The recorded Qwen step is no longer active; stale server state was removed.")
        return 0
    completed = run_command(["scancel", "--signal=TERM", step_target], timeout=30)
    if completed is None or completed.returncode != 0:
        detail = "scancel unavailable" if completed is None else completed.stderr.strip()
        print("ERROR: could not signal Qwen step {}: {}".format(step_target, detail), file=sys.stderr)
        return 3
    for _ in range(20):
        active = run_command(["scontrol", "show", "step", step_target], timeout=10)
        if active is None:
            print("ERROR: lost access to scontrol while checking Qwen shutdown.", file=sys.stderr)
            return 3
        if active.returncode != 0:
            detail = (active.stderr or active.stdout).strip().lower()
            if "invalid job" not in detail and "not found" not in detail:
                print("ERROR: could not verify Qwen shutdown: {}".format(detail), file=sys.stderr)
                return 3
            _remove_server_state(token)
            print("Stopped Qwen server step {}; allocation {} remains active.".format(step_target, job_id))
            return 0
        time.sleep(0.5)
    completed = run_command(["scancel", "--signal=KILL", step_target], timeout=30)
    if completed is None or completed.returncode != 0:
        detail = "scancel unavailable" if completed is None else completed.stderr.strip()
        print("ERROR: Qwen step {} did not stop and KILL failed: {}".format(step_target, detail), file=sys.stderr)
        return 3
    _remove_server_state(token)
    print("Force-stopped Qwen server step {}; allocation {} remains active.".format(step_target, job_id))
    return 0


def run_on_gpu(arguments):
    command = list(arguments.command)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        print("ERROR: no command was provided.", file=sys.stderr)
        return 2
    path = runtime_dir() / "current.json"
    try:
        state = read_state(path)
    except (OSError, ValueError, AllocationError) as exc:
        print("ERROR: no usable allocation state: {}".format(exc), file=sys.stderr)
        return 1
    job = query_job(state.get("job_id"))
    marker = managed_marker()
    if (
        job is None
        or normalize_job_state(job.get("job_state")) != "RUNNING"
        or not job_owned_and_managed(job, owner_uid(), marker)
        or state.get("managed_marker") != marker
    ):
        print("ERROR: recorded allocation is not a running, owned Dr.ICS job.", file=sys.stderr)
        return 1
    node = _job_node(job)
    try:
        inspection = inspect_allocated_gpu(job["job_id"], node)
    except AllocationError as exc:
        print("ERROR: allocation GPU verification failed: {}".format(exc), file=sys.stderr)
        return 1
    if not vram_suitable(inspection.get("gpus", []), int(state["gpu_count"]), int(state["minimum_vram_gib"])):
        print("ERROR: allocation no longer meets its recorded GPU policy.", file=sys.stderr)
        return 1
    srun = [
        "srun", "--jobid={}".format(int(job["job_id"])), "--nodes=1", "--ntasks=1",
        "--nodelist={}".format(node), "--overlap", "--chdir={}".format(os.getcwd()), "--",
    ] + command
    try:
        completed = subprocess.run(srun, check=False)
    except OSError as exc:
        print("ERROR: could not execute srun: {}".format(exc), file=sys.stderr)
        return 127
    if completed.returncode < 0:
        return 128 + abs(completed.returncode)
    return completed.returncode


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)

    allocate_parser = subparsers.add_parser("allocate", help="find or create a verified allocation")
    allocate_parser.add_argument("--min-vram", type=lambda value: _validate_positive(value, "--min-vram"), default=_validate_positive(os.environ.get("DRICS_MIN_GPU_MEMORY_GIB", "32"), "DRICS_MIN_GPU_MEMORY_GIB"), metavar="GIB")
    allocate_parser.add_argument("--gpus", type=lambda value: _validate_positive(value, "--gpus"), default=_validate_positive(os.environ.get("DRICS_GPU_COUNT", "1"), "DRICS_GPU_COUNT"))
    allocate_parser.add_argument("--walltime", default=os.environ.get("DRICS_GPU_WALLTIME", "04:00:00"))
    allocate_parser.add_argument("--cpus", type=lambda value: _validate_positive(value, "--cpus"), default=_validate_positive(os.environ.get("DRICS_GPU_CPUS", "8"), "DRICS_GPU_CPUS"))
    allocate_parser.add_argument("--mem", default=os.environ.get("DRICS_GPU_MEMORY", "32G"))
    allocate_parser.add_argument("--job-name", default=os.environ.get("DRICS_GPU_JOB_NAME", "drics-llm"))
    allocate_parser.add_argument("--gpu-type", default=os.environ.get("DRICS_GPU_GRES", "") or None)
    allocate_parser.add_argument("--partitions", default=os.environ.get("DRICS_GPU_PARTITIONS", DEFAULT_PARTITIONS), help="ordered PARTITION:ACCOUNT pairs")
    wait_group = allocate_parser.add_mutually_exclusive_group()
    wait_group.add_argument("--wait", dest="wait", action="store_true")
    wait_group.add_argument("--no-wait", dest="wait", action="store_false")
    allocate_parser.set_defaults(wait=True)
    allocate_parser.add_argument("--wait-seconds", type=int, default=int(os.environ.get("DRICS_GPU_ALLOCATION_WAIT_SECONDS", "60")))
    allocate_parser.add_argument("--poll-seconds", type=float, default=float(os.environ.get("DRICS_GPU_ALLOCATION_POLL_SECONDS", "4")))
    allocate_parser.add_argument("--dry-run", action="store_true")
    allocate_parser.set_defaults(handler=allocate)

    status_parser = subparsers.add_parser("status", help="verify current allocation")
    status_parser.add_argument("--no-recheck", action="store_true", help="skip nvidia-smi recheck (Slurm state only)")
    status_parser.set_defaults(handler=status)

    release_parser = subparsers.add_parser("release", help="release one recorded allocation")
    release_parser.add_argument("--job-id", type=int)
    release_parser.set_defaults(handler=release)

    stop_parser = subparsers.add_parser("stop-server", help="stop only the recorded Qwen server step")
    stop_parser.set_defaults(handler=stop_server)

    run_parser = subparsers.add_parser("run", help="run a command in the current allocation")
    run_parser.add_argument("command", nargs=argparse.REMAINDER)
    run_parser.set_defaults(handler=run_on_gpu)

    inspect_parser = subparsers.add_parser("_inspect", help=argparse.SUPPRESS)
    inspect_parser.set_defaults(handler=lambda arguments: internal_inspect())
    return parser


def main(argv=None):
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        return int(arguments.handler(arguments))
    except AllocationError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        if arguments.operation == "allocate":
            _print_not_ready("ALLOCATION_ERROR")
        return 3
    except KeyboardInterrupt:
        print("ERROR: interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
