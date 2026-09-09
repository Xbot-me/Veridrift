from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from guardrail.runtime.local_process import find_free_port
from guardrail.workload.generator import HttpWorkloadGenerator


def test_percentile_calculation():
    gen = HttpWorkloadGenerator()
    latencies = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    dist = gen._calculate_latency_distribution(latencies)
    assert dist.p50_ms == 55.0  # linear interpolation of 10 items
    assert dist.p90_ms == 91.0
    assert dist.p95_ms == 95.5
    assert dist.min_ms == 10.0
    assert dist.max_ms == 100.0


def test_empty_percentile_calculation():
    gen = HttpWorkloadGenerator()
    dist = gen._calculate_latency_distribution([])
    assert dist.p50_ms == 0.0
    assert dist.p99_ms == 0.0


@pytest.mark.asyncio
async def test_workload_stage_execution():
    port = find_free_port(5600)

    class DummyHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/error":
                self.send_response(500)
            elif self.path == "/notfound":
                self.send_response(404)
            else:
                self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("127.0.0.1", port), DummyHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        gen = HttpWorkloadGenerator()
        base_url = f"http://127.0.0.1:{port}"
        # Test short stage: 20 RPS for 0.5 second
        metrics = await gen.generate_async(
            target_url=f"{base_url}/",
            target_rps=20.0,
            duration_seconds=0.5,
        )

        assert metrics.total_requests > 0
        assert metrics.successful_requests > 0
        assert metrics.error_rate == 0.0
        assert metrics.latency.p50_ms >= 0

        # Test error path
        err_metrics = await gen.generate_async(
            target_url=f"{base_url}/error",
            target_rps=10.0,
            duration_seconds=0.3,
        )
        assert err_metrics.failed_requests > 0
        assert err_metrics.error_rate > 0.9
        assert err_metrics.server_errors == err_metrics.failed_requests

        # 4xx responses are CLIENT errors: they must never poison the production
        # error rate (this is what previously fabricated a "Hard Failure Boundary"
        # from a nonexistent endpoint returning 404).
        client_metrics = await gen.generate_async(
            target_url=f"{base_url}/notfound",
            target_rps=10.0,
            duration_seconds=0.3,
        )
        assert client_metrics.failed_requests > 0
        assert client_metrics.client_errors == client_metrics.failed_requests
        assert client_metrics.error_rate == 0.0
        assert client_metrics.client_error_rate > 0.9

        # Also test sync wrapper
        sync_metrics = gen.generate(
            target_url=f"{base_url}/",
            target_rps=10.0,
            duration_seconds=0.3,
        )
        assert sync_metrics.total_requests > 0
    finally:
        server.shutdown()
        server.server_close()
