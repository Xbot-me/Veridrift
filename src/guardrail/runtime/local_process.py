from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

try:
    import psutil
except ImportError:
    psutil = None

from guardrail.models.measurement import ResourceMetrics
from guardrail.models.target import Target
from guardrail.runtime.adapter import RuntimeAdapter, RuntimeInstance

logger = logging.getLogger(__name__)


def find_free_port(start_port: int = 5050) -> int:
    """Find an available local TCP port."""
    for p in range(start_port, start_port + 200):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LocalProcessRuntimeAdapter(RuntimeAdapter):
    """
    Runs the target application as an isolated local background process.
    Provides immediate zero-dependency verification without requiring a Docker daemon.
    """

    @property
    def name(self) -> str:
        return "local_process"

    def is_available(self) -> bool:
        """Return whether this host can launch a local Python process."""
        try:
            completed = subprocess.run(
                [sys.executable, "--version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
            return completed.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def start(
        self,
        target: Target,
        port: int | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> RuntimeInstance:
        """Start target application as a local subprocess."""
        target_path = Path(target.path).resolve()
        selected_port = port or find_free_port()

        # Find entrypoint
        cmd: list[str] = []
        if (target_path / "app.py").exists():
            cmd = [sys.executable, "app.py"]
        elif (target_path / "main.py").exists():
            cmd = [sys.executable, "main.py"]
        elif target.entry_points:
            cmd = [sys.executable, target.entry_points[0]]
        else:
            # Look for any python file that looks like a server
            py_files = list(target_path.glob("*.py"))
            if py_files:
                cmd = [sys.executable, py_files[0].name]
            else:
                raise RuntimeError(f"No runnable entrypoint found in {target_path}")

        # Prepare environment
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PORT"] = str(selected_port)
        env["FLASK_RUN_PORT"] = str(selected_port)
        env["HOST"] = "127.0.0.1"
        if env_vars:
            env.update(env_vars)

        logger.info("Starting local process: %s on port %d", " ".join(cmd), selected_port)
        proc = subprocess.Popen(
            cmd,
            cwd=str(target_path),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        instance = RuntimeInstance(
            instance_id=f"proc_{proc.pid}",
            target=target,
            host="127.0.0.1",
            port=selected_port,
            base_url=f"http://127.0.0.1:{selected_port}",
            process_handle=proc,
            env_vars=env,
            metadata={"pid": proc.pid, "command": cmd},
        )
        return instance

    def stop(self, instance: RuntimeInstance) -> None:
        """Terminate the running subprocess and all child processes."""
        proc: subprocess.Popen | None = instance.process_handle
        if not proc:
            return

        pid = proc.pid
        if psutil:
            try:
                parent = psutil.Process(pid)
                for child in parent.children(recursive=True):
                    try:
                        child.terminate()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                parent.terminate()
                parent.wait(timeout=3.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        else:
            try:
                proc.terminate()
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def health(
        self,
        instance: RuntimeInstance,
        timeout_seconds: float = 10.0,
        path: str = "/",
    ) -> bool:
        """Poll the instance until it responds or times out."""
        proc: subprocess.Popen | None = instance.process_handle
        start_time = time.time()

        # Candidate endpoints to check for responsiveness
        candidate_paths = [path]
        if hasattr(instance.target, "endpoints") and instance.target.endpoints:
            for ep in instance.target.endpoints:
                if ep.startswith("/") and ep not in candidate_paths:
                    candidate_paths.append(ep)

        with httpx.Client(timeout=1.0) as client:
            while time.time() - start_time < timeout_seconds:
                # Check if process terminated prematurely
                if proc and proc.poll() is not None:
                    stderr = proc.stderr.read() if proc.stderr else ""
                    logger.error(
                        "Application process exited prematurely with code %d: %s",
                        proc.returncode,
                        stderr,
                    )
                    return False

                for p in candidate_paths:
                    try:
                        res = client.get(f"{instance.base_url}{p}")
                        # If server responded with any valid HTTP status code, it's alive!
                        if res.status_code < 500:
                            logger.info(
                                "Health check succeeded on %s (HTTP %d)", p, res.status_code
                            )
                            return True
                    except (httpx.ConnectError, httpx.TimeoutException, OSError):
                        pass

                time.sleep(0.2)

        return False

    def get_metrics(self, instance: RuntimeInstance) -> ResourceMetrics:
        """Extract CPU and memory metrics for the running process."""
        proc: subprocess.Popen | None = instance.process_handle
        now = datetime.now(UTC)

        if not proc or not psutil:
            return ResourceMetrics(
                timestamp=now,
                cpu_percent=0.0,
                memory_mb=0.0,
            )

        try:
            p = psutil.Process(proc.pid)
            cpu = p.cpu_percent(interval=None)
            mem = p.memory_info().rss / (1024 * 1024)  # MB

            # Include children if any
            for child in p.children(recursive=True):
                try:
                    cpu += child.cpu_percent(interval=None)
                    mem += child.memory_info().rss / (1024 * 1024)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            mem_percent = None
            try:
                total_mem = psutil.virtual_memory().total / (1024 * 1024)
                if total_mem > 0:
                    mem_percent = round(mem / total_mem * 100.0, 2)
            except Exception:
                pass

            num_fds = (
                getattr(p, "num_handles", lambda: None)() if hasattr(p, "num_handles") else None
            )

            return ResourceMetrics(
                timestamp=now,
                cpu_percent=round(cpu, 2),
                memory_mb=round(mem, 2),
                memory_percent=mem_percent,
                open_file_descriptors=num_fds,
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return ResourceMetrics(timestamp=now, cpu_percent=0.0, memory_mb=0.0)

    def get_logs(self, instance: RuntimeInstance) -> str:
        """Return captured logs."""
        proc: subprocess.Popen | None = instance.process_handle
        if not proc:
            return ""
        logs = []
        if proc.stdout and proc.stdout.readable():
            try:
                logs.append(proc.stdout.read())
            except Exception:
                pass
        if proc.stderr and proc.stderr.readable():
            try:
                logs.append(proc.stderr.read())
            except Exception:
                pass
        return "\n".join(logs)
