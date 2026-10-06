"""Resource observations must not become session control or a second sampler per client."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from agent_orchestrator import dashboard, resources


def sample(at=100, total=100, idle=40):
    return {key: {"value": value, "observed_at": at, "error": ""} for key, value in {
        "cpu": {"total": total, "idle": idle, "logical_cpus": 8},
        "memory": {"total_bytes": 1000, "available_bytes": 300},
        "swap": {"total_bytes": 500, "used_bytes": 50},
        "outputs_disk": {"total_bytes": 2000, "free_bytes": 1500},
        "projects_disk": {"total_bytes": 2000, "free_bytes": 1500},
    }.items()}


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.monitor = resources.ResourceMonitor(Path("/fixture/output"), Path("/fixture/project"))

    def test_real_worker_without_site_packages_reports_missing_dependency(self):
        # -S reproduces an actual interpreter without installed psutil, even
        # when the developer/test environment has all dependencies installed.
        completed = subprocess.run(
            [sys.executable, "-S", resources.__file__, "/fixture/output", "/fixture/project"],
            capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        sample_data = json.loads(completed.stdout)
        self.assertTrue(all(item["error"] == "dependency_missing" for item in sample_data.values()))
        self.assertNotIn("Traceback", completed.stderr)
        with patch.object(resources.subprocess, "run", return_value=completed):
            self.monitor._sample()
        for item in self.monitor.snapshot()["metrics"].values():
            self.assertEqual(item["status"], "unavailable")
            self.assertEqual(item["error"], "dependency_missing")
            self.assertIsNone(item["observed_at"])
            self.assertIsNone(item["value"])

    def test_missing_dependency_retains_old_evidence_and_can_recover(self):
        self.monitor._accept(sample())
        failed = {key: {"value": None, "error": "dependency_missing"} for key in resources.METRICS}
        self.monitor._accept(failed)
        item = self.monitor.snapshot()["metrics"]["memory"]
        self.assertEqual(item["observed_at"], 100)
        self.assertEqual(item["value"]["available_bytes"], 300)
        self.assertEqual(item["error"], "dependency_missing")
        self.monitor._accept(sample(time.time()))
        self.assertEqual(self.monitor.snapshot()["metrics"]["memory"]["status"], "fresh")

    def test_import_failure_is_sanitized_and_distinct_from_missing_package(self):
        import builtins
        original = builtins.__import__
        for failure in (ImportError("private native module path"),
                        ModuleNotFoundError("private path", name="other_dependency")):
            def import_module(name, *args, **kwargs):
                if name == "psutil":
                    raise failure
                return original(name, *args, **kwargs)
            with patch.object(builtins, "__import__", side_effect=import_module):
                data = resources.collect("/fixture/output", "/fixture/project")
            self.assertTrue(all(item["error"] == "dependency_unavailable" for item in data.values()))
            self.assertNotIn("private", json.dumps(data))

    def test_cpu_normalized_deltas_not_first_sample_zero(self):
        self.monitor._accept(sample())
        self.assertIsNone(self.monitor.snapshot()["metrics"]["cpu"]["value"])
        self.monitor._accept(sample(105, 180, 60))
        self.assertEqual(self.monitor.snapshot()["metrics"]["cpu"]["value"],
                         {"percent": 75, "logical_cpus": 8})

    def test_counter_reset_and_sleep_gap_require_new_baseline(self):
        for next_sample in (sample(105, 80, 30), sample(140, 180, 60), sample(99, 180, 60)):
            self.monitor._accept(sample())
            self.monitor._accept(next_sample)
            self.assertEqual(self.monitor.snapshot()["metrics"]["cpu"]["error"], "warming_up")

    def test_partial_failure_retains_original_time_and_expires(self):
        with patch.object(resources.time, "time", return_value=100), \
                patch.object(resources.time, "monotonic", return_value=100):
            self.monitor._accept(sample())
        partial = sample(105)
        partial["memory"] = {"value": None, "error": "unavailable"}
        with patch.object(resources.time, "time", return_value=105), \
                patch.object(resources.time, "monotonic", return_value=105):
            self.monitor._accept(partial)
            value = self.monitor.snapshot()["metrics"]
        self.assertEqual(value["memory"]["observed_at"], 100)
        self.assertEqual(value["memory"]["status"], "unavailable")
        self.assertEqual(value["swap"]["status"], "fresh")
        # Wall-clock sleep OR monotonic time makes samples stale, including clock rollback.
        for wall, mono in ((116, 106), (90, 116)):
            with patch.object(resources.time, "time", return_value=wall), \
                    patch.object(resources.time, "monotonic", return_value=mono):
                self.assertEqual(self.monitor.snapshot()["metrics"]["memory"]["status"], "stale")

    def test_disabled_never_starts_collection(self):
        with patch.dict(resources.os.environ, {"ORCH_RESOURCE_MONITOR_ENABLED": "0"}):
            monitor = resources.ResourceMonitor(Path("/tmp"), Path("/tmp"))
        with patch.object(monitor, "_sample") as collect:
            monitor.start()
            monitor.stop()
        collect.assert_not_called()
        self.assertFalse(monitor.snapshot()["enabled"])
        self.assertEqual(monitor.snapshot()["metrics"]["cpu"]["status"], "disabled")

    def test_start_is_idempotent_cached_reads_do_not_sample_or_mutate(self):
        entered, release = threading.Event(), threading.Event()
        def block():
            entered.set()
            release.wait(2)
        with patch.object(self.monitor, "_sample", side_effect=block) as collect:
            try:
                self.monitor.start()
                self.assertTrue(entered.wait(1))
                self.monitor.start()
                for _ in range(20):
                    self.monitor.snapshot()["metrics"].clear()
                self.assertEqual(len(self.monitor.snapshot()["metrics"]), 5)
                self.assertEqual(collect.call_count, 1)
            finally:
                release.set()
                self.monitor.stop()
        self.assertFalse(self.monitor._thread.is_alive())

    def test_timeout_and_invalid_worker_output_do_not_leak_or_kill_monitor(self):
        for failure in (subprocess.TimeoutExpired("private-command", 2),
                        subprocess.CalledProcessError(1, "private-command")):
            with patch.object(resources.subprocess, "run", side_effect=failure) as run:
                self.monitor._sample()
            self.assertEqual(run.call_args.kwargs["timeout"], 2)
            self.assertNotIn("private-command", json.dumps(self.monitor.snapshot()))
        with patch.object(resources.subprocess, "run", return_value=SimpleNamespace(stdout='{"cpu": 9}')):
            self.monitor._sample()
        self.assertEqual(self.monitor.snapshot()["metrics"]["cpu"]["status"], "unavailable")

    def test_unsupported_platform_does_not_invent_observations(self):
        self.monitor.platform = "Unsupported"
        with patch.object(resources.subprocess, "run") as run:
            self.monitor._sample()
        run.assert_not_called()
        self.assertIsNone(self.monitor.snapshot()["metrics"]["memory"]["value"])

    def test_real_hung_collector_is_killed_with_no_overlapping_child(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = Path(directory) / "collector.py"
            worker.write_text("import time\ntime.sleep(30)\n")
            with patch.object(resources, "__file__", str(worker)), \
                    patch.object(resources, "TIMEOUT", 0.1):
                started = time.monotonic()
                self.monitor._sample()
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(self.monitor.snapshot()["metrics"]["memory"]["error"], "timeout")

    def test_macos_linux_provider_units_and_independent_failure(self):
        for counters, expected in (({"user": 20, "system": 10, "idle": 70}, 100),
                                   ({"user": 20, "system": 10, "idle": 70,
                                     "iowait": 5, "guest": 3, "guest_nice": 2}, 105)):
            provider = Mock()
            provider.cpu_times.return_value._asdict.return_value = counters
            provider.cpu_count.return_value = 8
            provider.virtual_memory.return_value = SimpleNamespace(total=1000, available=200)
            provider.swap_memory.side_effect = PermissionError("secret")
            provider.disk_usage.side_effect = [SimpleNamespace(total=2000, free=500), FileNotFoundError("private")]
            value = resources.collect("output-fixture", "project-fixture", provider)
            self.assertEqual(value["cpu"]["value"]["total"], expected)
            self.assertEqual(value["memory"]["value"]["available_bytes"], 200)
            self.assertEqual(value["outputs_disk"]["value"]["free_bytes"], 500)
            self.assertIsNone(value["projects_disk"]["observed_at"])
            self.assertEqual(value["swap"]["error"], "permission_denied")
            self.assertEqual(value["projects_disk"]["error"], "path_missing")
            self.assertNotIn("secret", json.dumps(value))

    def test_api_is_authenticated_cached_no_store_and_not_public_health(self):
        with tempfile.TemporaryDirectory() as directory:
            app = dashboard.create_app(Path(directory), token="fixture-token", remote_nodes_enabled=False)
            with patch.object(app.state.resources, "start") as start, \
                    patch.object(app.state.resources, "stop") as stop, \
                    patch.object(app.state.resources, "_sample") as collect, TestClient(app) as client:
                self.assertEqual(client.get("/api/resources").status_code, 401)
                public = client.get("/api/health")
                self.assertEqual(public.status_code, 200)
                self.assertNotIn("metrics", public.json())
                for _ in range(3):
                    response = client.get("/api/resources", headers={"Authorization": "Bearer fixture-token"})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.headers["cache-control"], "no-store")
                    self.assertEqual(response.json()["scope"], "dashboard_host")
                self.assertEqual(client.post("/api/resources").status_code, 405)
            start.assert_called_once()
            stop.assert_called_once()
            collect.assert_not_called()
