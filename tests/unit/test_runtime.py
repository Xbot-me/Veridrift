from __future__ import annotations

import time
from pathlib import Path

from guardrail.models.target import Target
from guardrail.runtime.engine import RuntimeEngine
from guardrail.runtime.local_process import LocalProcessRuntimeAdapter, find_free_port


def test_find_free_port():
    port1 = find_free_port(start_port=5200)
    assert 5200 <= port1 < 6000
    port2 = find_free_port(start_port=port1 + 1)
    assert port2 != port1


def test_local_process_runtime_adapter_is_available():
    adapter = LocalProcessRuntimeAdapter()
    assert adapter.name == "local_process"
    assert adapter.is_available() is True


def test_runtime_engine_is_available_no_crash():
    """availability probing must return True/False cleanly, never raise."""
    engine = RuntimeEngine()
    result = engine.is_available()
    assert isinstance(result, bool)
    assert result is True


def test_runtime_engine_reports_local_process():
    """local_process is the zero-dependency runtime and should be reported."""
    engine = RuntimeEngine()
    runtimes = engine.available_runtimes()
    assert "local_process" in runtimes


def test_runtime_engine_no_runtimes_is_false(monkeypatch):
    """If every runtime probe fails, availability must report False cleanly."""

    def _explode(self):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "guardrail.runtime.local_process.LocalProcessRuntimeAdapter.is_available",
        _explode,
    )
    monkeypatch.setattr(RuntimeEngine, "is_docker_available", lambda self: False)
    engine = RuntimeEngine()
    assert engine.available_runtimes() == []
    assert engine.is_available() is False


def test_runtime_engine_reports_docker_when_available(monkeypatch):
    engine = RuntimeEngine()
    monkeypatch.setattr(RuntimeEngine, "is_docker_available", lambda self: True)
    runtimes = engine.available_runtimes()
    assert "docker" in runtimes


def test_local_process_lifecycle(tmp_path: Path):
    # Create a simple python http server script
    server_script = tmp_path / "app.py"
    server_script.write_text(
        """from http.server import HTTPServer, BaseHTTPRequestHandler
import os

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')
    def log_message(self, format, *args):
        pass

port = int(os.environ.get("PORT", 8080))
server = HTTPServer(("127.0.0.1", port), Handler)
server.serve_forever()
""",
        encoding="utf-8",
    )

    target = Target(
        path=str(tmp_path),
        name="test_local_app",
        languages=["python"],
        frameworks=[],
        package_managers=[],
        endpoints=["/"],
    )

    adapter = LocalProcessRuntimeAdapter()
    port = find_free_port(5500)
    instance = adapter.start(target, port=port)

    try:
        assert instance.port == port
        assert instance.base_url == f"http://127.0.0.1:{port}"
        assert instance.process_handle is not None
        assert instance.process_handle.poll() is None

        # Check health
        healthy = adapter.health(instance, timeout_seconds=4.0, path="/")
        assert healthy is True

        # Check resource metrics
        metrics = adapter.get_metrics(instance)
        assert metrics is not None
        assert metrics.memory_mb >= 0.0

    finally:
        adapter.stop(instance)
        time.sleep(0.5)
        # Ensure stopped
        assert instance.process_handle.poll() is not None
