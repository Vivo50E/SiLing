"""Bounded, read-only host observations. No session or process enumeration."""

from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import threading
import time


METRICS = ("cpu", "memory", "swap", "outputs_disk", "projects_disk")
INTERVAL = 5.0
TIMEOUT = 2.0
MAX_AGE = 15.0


def collect(outputs: str, projects: str, provider=None) -> dict:
    """Run only in the disposable child; injected provider enables OS fixtures."""
    if provider is None:
        try:
            import psutil as provider
        except (ImportError, OSError) as exc:
            error = ("dependency_missing" if isinstance(exc, ModuleNotFoundError)
                     and exc.name == "psutil" else "dependency_unavailable")
            # Return a safe protocol result, never raw import paths or stderr.
            return {key: {"value": None, "observed_at": None, "error": error}
                    for key in METRICS}

    def cpu():
        values = provider.cpu_times()._asdict()
        # Linux guest counters are already included in user/nice.
        total = sum(values.values()) - values.get("guest", 0) - values.get("guest_nice", 0)
        idle = values.get("idle", 0) + values.get("iowait", 0)
        return {"total": total, "idle": idle, "logical_cpus": provider.cpu_count()}

    def memory():
        value = provider.virtual_memory()
        return {"total_bytes": value.total, "available_bytes": value.available}

    def swap():
        value = provider.swap_memory()
        return {"total_bytes": value.total, "used_bytes": value.used}

    def disk(path):
        # Missing configured directories are unknown, not silently the root volume.
        value = provider.disk_usage(path)
        return {"total_bytes": value.total, "free_bytes": value.free}

    result = {}
    for key, read in (("cpu", cpu), ("memory", memory), ("swap", swap),
                      ("outputs_disk", lambda: disk(outputs)),
                      ("projects_disk", lambda: disk(projects))):
        try:
            result[key] = {"value": read(), "observed_at": time.time(), "error": ""}
        except Exception as exc:
            # Do not return paths, environment or raw exception messages.
            error = ("path_missing" if isinstance(exc, FileNotFoundError)
                     else "permission_denied" if isinstance(exc, PermissionError)
                     else "unavailable")
            result[key] = {"value": None, "observed_at": None, "error": error}
    return result


class ResourceMonitor:
    def __init__(self, outputs: Path, projects: Path, *, enabled: bool | None = None):
        self.enabled = (os.environ.get("ORCH_RESOURCE_MONITOR_ENABLED", "1").lower()
                        not in {"0", "false", "off"}) if enabled is None else enabled
        self.host = socket.gethostname()
        self.platform = platform.system()
        self._paths = (str(outputs.absolute()), str(projects.absolute()))
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._previous_cpu = None
        self._metrics = {key: {"value": None, "observed_at": None,
                               "error": "pending", "source": "psutil"} for key in METRICS}
        self._received = {}

    def start(self) -> None:
        with self._lock:
            if not self.enabled or (self._thread and self._thread.is_alive()):
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True,
                                            name="siling-host-resources")
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=TIMEOUT + 1)

    def _loop(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            self._sample()
            self._stop.wait(max(0.1, INTERVAL - (time.monotonic() - started)))

    def _sample(self) -> None:
        error = "unavailable"
        try:
            if self.platform not in {"Darwin", "Linux"}:
                raise ValueError("unsupported platform")
            # Absolute script + selected interpreter also work in temporary worktrees.
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).absolute()), *self._paths],
                capture_output=True, text=True, timeout=TIMEOUT, check=True,
            )
            sample = json.loads(completed.stdout)
            if not isinstance(sample, dict):
                raise ValueError("invalid sample")
        except subprocess.TimeoutExpired:
            sample = {}
            error = "timeout"
        except Exception:
            sample = {}
        self._accept(sample, error)

    def _accept(self, sample: dict, error: str = "unavailable") -> None:
        monotonic = time.monotonic()
        with self._lock:
            for key in METRICS:
                item = sample.get(key, {})
                if not isinstance(item, dict):
                    item = {}
                value = item.get("value")
                observed = item.get("observed_at")
                required = {"cpu": ("total", "idle"),
                            "memory": ("total_bytes", "available_bytes"),
                            "swap": ("total_bytes", "used_bytes")}.get(
                                key, ("total_bytes", "free_bytes"))
                if (not isinstance(value, dict)
                        or not isinstance(observed, (float, int)) or not math.isfinite(observed)
                        or any(not isinstance(value.get(name), (float, int))
                               or not math.isfinite(value[name]) or value[name] < 0
                               for name in required)):
                    value = None
                failure = item.get("error") or error
                if key == "cpu":
                    previous = self._previous_cpu
                    self._previous_cpu = (value, observed) if value is not None else None
                    if value is not None:
                        failure = "warming_up"
                        if previous and 0 < observed - previous[1] <= MAX_AGE:
                            delta = value["total"] - previous[0]["total"]
                            idle = value["idle"] - previous[0]["idle"]
                            if delta > 0 and 0 <= idle <= delta:
                                value = {"percent": round(100 * (delta - idle) / delta, 1),
                                         "logical_cpus": value.get("logical_cpus")}
                            else:
                                value = None
                        else:
                            value = None
                if value is not None and observed is not None:
                    self._metrics[key].update(value=value, observed_at=observed, error="")
                    self._received[key] = monotonic
                else:
                    # Keep last value/time, but the failed metric is NOT fresh.
                    self._metrics[key]["error"] = failure

    def snapshot(self) -> dict:
        now, monotonic = time.time(), time.monotonic()
        with self._lock:
            metrics = copy.deepcopy(self._metrics)
            for key, item in metrics.items():
                observed = item["observed_at"]
                age = max(0, now - observed, monotonic - self._received[key]) if observed else None
                item["age_s"] = round(age, 2) if age is not None else None
                item["status"] = (
                    "disabled" if not self.enabled else
                    ("unknown" if item["error"] in {"pending", "warming_up"}
                     else "unavailable") if observed is None else
                    "stale" if age >= MAX_AGE else
                    "unavailable" if item["error"] else "fresh"
                )
            return {"schema_version": 1, "enabled": self.enabled, "host": self.host,
                    "platform": self.platform, "scope": "dashboard_host",
                    "interval_s": INTERVAL, "max_age_s": MAX_AGE, "metrics": metrics}


if __name__ == "__main__":
    print(json.dumps(collect(*sys.argv[1:3])))
