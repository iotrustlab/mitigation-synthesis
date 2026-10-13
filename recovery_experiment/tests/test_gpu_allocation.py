import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import Mock, patch


REPO_ROOT = Path(__file__).resolve().parents[2]
GPU_ALLOCATION_PATH = REPO_ROOT / "scripts" / "llm" / "gpu_allocation.py"


def _load_gpu_allocation_module():
    spec = importlib.util.spec_from_file_location(
        "drics_gpu_allocation", str(GPU_ALLOCATION_PATH)
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load {}".format(GPU_ALLOCATION_PATH))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gpu_allocation = _load_gpu_allocation_module()


class FreeGpuParsingTests(unittest.TestCase):
    def test_counts_and_aggregates_freegpu_models(self):
        report = """
NOTE: advisory output only
SUMMARY: soc-gpu-np
a6000 (x2)
a100 (x8)
a6000 (x1)
"""

        count, models = gpu_allocation.parse_freegpus(report)

        self.assertEqual(count, 11)
        self.assertEqual(models, {"a6000": 3, "a100": 8})

    def test_empty_and_malformed_lines_do_not_create_free_gpus(self):
        report = """
SUMMARY: notchpeak-gpu
Unable to obtain GPU information.
v100 (xmany)
3090 x4
"""

        count, models = gpu_allocation.parse_freegpus(report)

        self.assertEqual(count, 0)
        self.assertEqual(models, {})


class GpuInventoryTests(unittest.TestCase):
    def test_parses_nvidia_smi_csv_without_splitting_quoted_names(self):
        report = (
            "NVIDIA RTX A6000, 49140, GPU-aaaa\n"
            '"NVIDIA H100, PCIe", 81559, GPU-bbbb\n'
        )

        gpus = gpu_allocation.parse_gpu_csv(report)

        self.assertEqual(len(gpus), 2)
        self.assertEqual(gpus[0]["name"], "NVIDIA RTX A6000")
        self.assertEqual(gpus[0]["memory_mib"], 49140)
        self.assertEqual(gpus[0]["uuid"], "GPU-aaaa")
        self.assertEqual(gpus[1]["name"], "NVIDIA H100, PCIe")
        self.assertEqual(gpus[1]["memory_mib"], 81559)
        self.assertEqual(gpus[1]["uuid"], "GPU-bbbb")

    def test_rejects_malformed_gpu_memory(self):
        with self.assertRaises(ValueError):
            gpu_allocation.parse_gpu_csv(
                "NVIDIA RTX A6000, forty-eight-gib, GPU-aaaa\n"
            )

    def test_vram_threshold_uses_1024_mib_per_gib(self):
        at_threshold = [
            {"name": "test", "memory_mib": 32768, "uuid": "GPU-one"}
        ]
        below_threshold = [
            {"name": "test", "memory_mib": 32767, "uuid": "GPU-one"}
        ]

        self.assertTrue(gpu_allocation.vram_suitable(at_threshold, 1, 32))
        self.assertFalse(gpu_allocation.vram_suitable(below_threshold, 1, 32))

    def test_vram_check_requires_enough_gpus_and_checks_each_required_gpu(self):
        one_gpu = [
            {"name": "large", "memory_mib": 49140, "uuid": "GPU-one"}
        ]
        mixed_pair = [
            {"name": "large", "memory_mib": 49140, "uuid": "GPU-one"},
            {"name": "small", "memory_mib": 24576, "uuid": "GPU-two"},
        ]

        self.assertFalse(gpu_allocation.vram_suitable(one_gpu, 2, 32))
        self.assertFalse(gpu_allocation.vram_suitable(mixed_pair, 2, 32))


class SlurmStateTests(unittest.TestCase):
    def test_normalizes_slurm_json_list_and_text_states(self):
        self.assertEqual(gpu_allocation.normalize_job_state(["RUNNING"]), "RUNNING")
        self.assertEqual(gpu_allocation.normalize_job_state("pending"), "PENDING")

    def test_missing_slurm_state_is_unknown(self):
        self.assertEqual(gpu_allocation.normalize_job_state([]), "UNKNOWN")
        self.assertEqual(gpu_allocation.normalize_job_state(None), "UNKNOWN")


class AllocationStateFileTests(unittest.TestCase):
    def _state(self, gpu_name="NVIDIA RTX A6000"):
        return {
            "schema_version": 1,
            "managed_marker": "drics-gpu-v1:1682728",
            "job_id": 7123456,
            "job_name": "drics-llm",
            "owner_uid": 1682728,
            "node": "notch001",
            "partition": "soc-gpu-np",
            "account": "soc-gpu-np",
            "gpu_count": 1,
            "gpu_name": gpu_name,
            "gpu_memory_mib": 49140,
            "minimum_vram_gib": 32,
            "walltime": "04:00:00",
            "created_at": "2026-09-26T12:00:00Z",
        }

    def test_write_and_read_state_replace_existing_files_atomically(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            json_path = directory / "current.json"
            env_path = directory / "current.env"
            json_path.write_text('{"incomplete":', encoding="utf-8")
            env_path.write_text("INCOMPLETE='yes'\n", encoding="utf-8")

            state = self._state()
            gpu_allocation.write_state(
                state, str(json_path), str(env_path)
            )

            self.assertEqual(gpu_allocation.read_state(str(json_path)), state)
            self.assertEqual(
                json.loads(json_path.read_text(encoding="utf-8")), state
            )
            self.assertFalse(list(directory.glob("*.tmp")))
            self.assertFalse(list(directory.glob(".*.tmp")))

            replacement = self._state(gpu_name="NVIDIA A100-SXM4-80GB")
            replacement["gpu_memory_mib"] = 81251
            gpu_allocation.write_state(
                replacement, str(json_path), str(env_path)
            )
            self.assertEqual(
                gpu_allocation.read_state(str(json_path)), replacement
            )

    def test_env_serialization_is_shell_safe_and_round_trips_spaces(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            touched_path = directory / "must-not-exist"
            hostile_name = "NVIDIA 'quoted' $(touch {})".format(touched_path)
            state = self._state(gpu_name=hostile_name)
            env_text = gpu_allocation.serialize_state_env(state)
            env_path = directory / "current.env"
            env_path.write_text(env_text, encoding="utf-8")

            output = subprocess.check_output(
                [
                    "bash",
                    "--noprofile",
                    "--norc",
                    "-c",
                    '. "$1"; printf "%s\\0%s\\0%s" '
                    '"$JOB_ID" "$GPU_NAME" "$GPU_MEMORY_MIB"',
                    "bash",
                    str(env_path),
                ]
            )

            values = output.decode("utf-8").split("\0")
            self.assertEqual(values, ["7123456", hostile_name, "49140"])
            self.assertFalse(touched_path.exists())


class ReuseAndCleanupPolicyTests(unittest.TestCase):
    MARKER = "drics-gpu-v1:1682728"
    UID = 1682728

    def _job(self, job_id=7123456, **overrides):
        job = {
            "job_id": job_id,
            "name": "drics-llm",
            "user_id": self.UID,
            "comment": self.MARKER,
            "job_state": ["RUNNING"],
            "nodes": "notch001",
            "partition": "soc-gpu-np",
            "account": "soc-gpu-np",
        }
        job.update(overrides)
        return job

    def test_reuses_only_running_exact_owner_name_and_marker_match(self):
        jobs = [
            self._job(job_id=1, comment="some-other-tool"),
            self._job(job_id=2, user_id=self.UID + 1),
            self._job(job_id=3, name="unrelated"),
            self._job(job_id=4, job_state=["PENDING"]),
            self._job(job_id=5),
        ]

        selected = gpu_allocation.choose_reusable_job(
            jobs, self.UID, "drics-llm", self.MARKER
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected["job_id"], 5)

    def test_similar_marker_is_not_treated_as_managed(self):
        jobs = [self._job(comment=self.MARKER + ":different-repository")]

        selected = gpu_allocation.choose_reusable_job(
            jobs, self.UID, "drics-llm", self.MARKER
        )

        self.assertIsNone(selected)

    def test_cleanup_allows_newly_submitted_or_recorded_managed_job(self):
        submitted_job = self._job(job_id=10)
        recorded_job = self._job(job_id=11)

        self.assertTrue(
            gpu_allocation.should_cancel_job(
                submitted_job, self.UID, self.MARKER, {10}, None
            )
        )
        self.assertTrue(
            gpu_allocation.should_cancel_job(
                recorded_job, self.UID, self.MARKER, set(), 11
            )
        )

    def test_cleanup_refuses_untracked_wrong_marker_or_wrong_owner_job(self):
        untracked_job = self._job(job_id=20)
        wrong_marker_job = self._job(job_id=21, comment="vscode-gpu")
        wrong_owner_job = self._job(job_id=22, user_id=self.UID + 1)

        self.assertFalse(
            gpu_allocation.should_cancel_job(
                untracked_job, self.UID, self.MARKER, set(), None
            )
        )
        self.assertFalse(
            gpu_allocation.should_cancel_job(
                wrong_marker_job, self.UID, self.MARKER, {21}, None
            )
        )
        self.assertFalse(
            gpu_allocation.should_cancel_job(
                wrong_owner_job, self.UID, self.MARKER, {22}, None
            )
        )


class AllocationTransitionTests(unittest.TestCase):
    """Exercise allocator transitions without contacting Slurm or CHPC."""

    UID = 1682728
    MARKER = "drics-gpu-v1:1682728:test-repository"

    def _arguments(self, dry_run=False):
        arguments = [
            "allocate",
            "--min-vram",
            "32",
            "--gpus",
            "1",
            "--walltime",
            "04:00:00",
            "--cpus",
            "8",
            "--mem",
            "32G",
            "--job-name",
            "drics-llm",
            "--partitions",
            "partition-a:account-a,partition-b:account-b",
            "--wait",
            "--wait-seconds",
            "1",
            "--poll-seconds",
            "0.01",
        ]
        if dry_run:
            arguments.append("--dry-run")
        return gpu_allocation.build_parser().parse_args(arguments)

    def _job(self, job_id, partition, state="RUNNING"):
        return {
            "job_id": int(job_id),
            "name": "drics-llm",
            "user_id": self.UID,
            "comment": self.MARKER,
            "job_state": [state],
            "state_reason": "None",
            "nodes": "{}-node".format(partition),
            "partition": partition,
            "account": "account-a" if partition == "partition-a" else "account-b",
            "cpus": 8,
            "memory_per_node": {"number": 32768},
            "time_limit": {"number": 240},
            "end_time": {"number": int(time.time()) + 14400},
            "gres_detail": ["gpu:1(IDX:0)"],
        }

    def _inspection(self, job_id, memory_mib):
        partition = "partition-a" if int(job_id) == 101 else "partition-b"
        return {
            "ok": True,
            "hostname": "{}-node".format(partition),
            "cuda_visible_devices": "0",
            "slurm_job_gpus": "0",
            "gpus": [
                {
                    "index": 0,
                    "uuid": "GPU-{}".format(job_id),
                    "name": "Mock GPU {}".format(job_id),
                    "memory_mib": int(memory_mib),
                }
            ],
        }

    def _enter_discovery_patches(self, stack):
        stack.enter_context(
            patch.object(
                gpu_allocation,
                "freegpu_report",
                return_value={
                    "ok": True,
                    "text": "mock-gpu (x1)",
                    "count": 1,
                    "models": {"mock-gpu": 1},
                },
            )
        )
        stack.enter_context(
            patch.object(gpu_allocation, "advertised_gpu_types", return_value={"mock-gpu"})
        )

        def partition_information(partition):
            account = "account-a" if partition == "partition-a" else "account-b"
            return {"accounts": {"allowed": account}}

        stack.enter_context(
            patch.object(
                gpu_allocation,
                "inspect_partition",
                side_effect=partition_information,
            )
        )
        stack.enter_context(patch.object(gpu_allocation, "owner_uid", return_value=self.UID))
        stack.enter_context(
            patch.object(gpu_allocation, "managed_marker", return_value=self.MARKER)
        )
        stack.enter_context(
            patch.object(gpu_allocation.getpass, "getuser", return_value="test-user")
        )

    def test_low_vram_job_is_cancelled_before_next_candidate_is_submitted(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            submitted = []
            cancelled = set()
            commands = []

            def fake_run_command(arguments, timeout=30, check=False, env=None):
                del timeout, check, env
                command = list(arguments)
                commands.append(command)
                if command[0] == "sbatch":
                    job_id = 101 + len(submitted)
                    partition = next(
                        item.split("=", 1)[1]
                        for item in command
                        if item.startswith("--partition=")
                    )
                    submitted.append((job_id, partition))
                    return subprocess.CompletedProcess(command, 0, "{}\n".format(job_id), "")
                if command[0] == "scancel":
                    cancelled.add(int(command[1]))
                    return subprocess.CompletedProcess(command, 0, "", "")
                self.fail("unexpected external command: {!r}".format(command))

            def fake_query_job(job_id):
                job_id = int(job_id)
                partition = dict(submitted)[job_id]
                state = "CANCELLED" if job_id in cancelled else "RUNNING"
                return self._job(job_id, partition, state=state)

            def fake_inspection(job_id, node):
                del node
                memory_mib = 24576 if int(job_id) == 101 else 49140
                return self._inspection(job_id, memory_mib)

            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    patch.dict(
                        os.environ,
                        {"DRICS_GPU_STATE_DIR": temporary_directory},
                    )
                )
                self._enter_discovery_patches(stack)
                stack.enter_context(patch.object(gpu_allocation, "query_jobs", return_value=[]))
                stack.enter_context(
                    patch.object(gpu_allocation, "query_job", side_effect=fake_query_job)
                )
                stack.enter_context(
                    patch.object(
                        gpu_allocation,
                        "inspect_allocated_gpu",
                        side_effect=fake_inspection,
                    )
                )
                stack.enter_context(
                    patch.object(gpu_allocation, "run_command", side_effect=fake_run_command)
                )
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                    io.StringIO()
                ):
                    result = gpu_allocation.allocate(self._arguments())

            self.assertEqual(result, 0)
            self.assertEqual(submitted, [(101, "partition-a"), (102, "partition-b")])
            self.assertEqual(cancelled, {101})
            self.assertEqual(
                [command[0] for command in commands],
                ["sbatch", "scancel", "sbatch"],
            )
            state = gpu_allocation.read_state(
                str(Path(temporary_directory) / "current.json")
            )
            self.assertEqual(state["job_id"], 102)
            rejected_record = gpu_allocation.read_state(
                str(Path(temporary_directory) / "jobs" / "101.json")
            )
            self.assertEqual(rejected_record["status"], "CANCELLED_AFTER_REJECTION")

    def test_cleanup_failure_stops_before_another_submission(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            submitted = []
            commands = []

            def fake_run_command(arguments, timeout=30, check=False, env=None):
                del timeout, check, env
                command = list(arguments)
                commands.append(command)
                if command[0] == "sbatch":
                    submitted.append(101)
                    return subprocess.CompletedProcess(command, 0, "101\n", "")
                if command[0] == "scancel":
                    return subprocess.CompletedProcess(
                        command, 1, "", "mock scancel failure"
                    )
                self.fail("unexpected external command: {!r}".format(command))

            def fake_query_job(job_id):
                return self._job(int(job_id), "partition-a")

            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    patch.dict(
                        os.environ,
                        {"DRICS_GPU_STATE_DIR": temporary_directory},
                    )
                )
                self._enter_discovery_patches(stack)
                stack.enter_context(patch.object(gpu_allocation, "query_jobs", return_value=[]))
                stack.enter_context(
                    patch.object(gpu_allocation, "query_job", side_effect=fake_query_job)
                )
                stack.enter_context(
                    patch.object(
                        gpu_allocation,
                        "inspect_allocated_gpu",
                        return_value=self._inspection(101, 24576),
                    )
                )
                stack.enter_context(
                    patch.object(gpu_allocation, "run_command", side_effect=fake_run_command)
                )
                stdout = io.StringIO()
                stderr = io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    result = gpu_allocation.allocate(self._arguments())

            self.assertEqual(result, 3)
            self.assertEqual(submitted, [101])
            self.assertEqual(
                [command[0] for command in commands], ["sbatch", "scancel"]
            )
            self.assertIn("refusing another submission", stderr.getvalue())
            self.assertIn("DRICS_GPU_REASON=REJECTED_JOB_CLEANUP_FAILED", stdout.getvalue())
            self.assertFalse((Path(temporary_directory) / "current.json").exists())

    def test_dry_run_never_invokes_sbatch_or_queries_jobs(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_command = Mock(side_effect=AssertionError("dry-run invoked an external command"))
            query_jobs = Mock(side_effect=AssertionError("dry-run queried jobs"))

            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    patch.dict(
                        os.environ,
                        {"DRICS_GPU_STATE_DIR": temporary_directory},
                    )
                )
                self._enter_discovery_patches(stack)
                stack.enter_context(patch.object(gpu_allocation, "run_command", run_command))
                stack.enter_context(patch.object(gpu_allocation, "query_jobs", query_jobs))
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(
                    io.StringIO()
                ):
                    result = gpu_allocation.allocate(self._arguments(dry_run=True))

            self.assertEqual(result, 0)
            run_command.assert_not_called()
            query_jobs.assert_not_called()
            self.assertIn("DRICS_GPU_REASON=DRY_RUN", stdout.getvalue())
            self.assertFalse((Path(temporary_directory) / "current.json").exists())

    def test_suitable_existing_managed_job_is_reused_without_sbatch(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            existing_job = self._job(77, "partition-a")
            run_command = Mock(side_effect=AssertionError("reuse invoked an external command"))

            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    patch.dict(
                        os.environ,
                        {"DRICS_GPU_STATE_DIR": temporary_directory},
                    )
                )
                self._enter_discovery_patches(stack)
                stack.enter_context(
                    patch.object(gpu_allocation, "query_jobs", return_value=[existing_job])
                )
                stack.enter_context(
                    patch.object(
                        gpu_allocation,
                        "inspect_allocated_gpu",
                        return_value=self._inspection(77, 49140),
                    )
                )
                stack.enter_context(patch.object(gpu_allocation, "run_command", run_command))
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(
                    io.StringIO()
                ):
                    result = gpu_allocation.allocate(self._arguments())

            self.assertEqual(result, 0)
            run_command.assert_not_called()
            self.assertIn("Reusing existing Dr.ICS GPU allocation", stdout.getvalue())
            state = gpu_allocation.read_state(
                str(Path(temporary_directory) / "current.json")
            )
            self.assertEqual(state["job_id"], 77)


if __name__ == "__main__":
    unittest.main()
