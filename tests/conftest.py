"""Shared test fixtures for Guardrail tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from guardrail.models.base import (
    Confidence,
    EvidenceType,
    RuleCategory,
    Severity,
    VerdictStatus,
)
from guardrail.models.environment import (
    DatabaseConfig,
    Environment,
    ResourceLimits,
)
from guardrail.models.evidence import Evidence
from guardrail.models.measurement import (
    DatabaseMetrics,
    LatencyDistribution,
    Measurement,
    RequestMetrics,
    ResourceMetrics,
)
from guardrail.models.policy import Policy
from guardrail.models.rule import Finding
from guardrail.models.run import RunMetadata, VerificationRun
from guardrail.models.target import DependencyInfo, ServiceInfo, Target
from guardrail.models.verdict import Verdict


@pytest.fixture
def sample_target() -> Target:
    """Create a sample target for testing."""
    return Target(
        path="/tmp/test-project",
        name="test-app",
        languages=["python"],
        frameworks=["flask"],
        package_managers=["pip"],
        services=[
            ServiceInfo(
                name="web",
                language="python",
                framework="flask",
                entry_point="app.py",
                port=5000,
            )
        ],
        dependencies=[
            DependencyInfo(
                name="postgresql",
                type="database",
                connection_info={"host": "localhost", "port": "5432"},
            )
        ],
        entry_points=["app.py"],
        endpoints=["/api/users", "/api/orders"],
        config_files=[".env", "config.yaml"],
        containers=["Dockerfile"],
        test_suites=["tests/"],
        build_systems=["pip"],
    )


@pytest.fixture
def sample_environment() -> Environment:
    """Create a sample environment for testing."""
    return Environment(
        name="test",
        resource_limits=ResourceLimits(
            cpu_cores=2.0,
            memory_mb=1024,
            pids_limit=256,
        ),
        databases={
            "main": DatabaseConfig(
                type="postgresql",
                image="postgres:16",
                port=5432,
                max_connections=100,
            )
        },
    )


@pytest.fixture
def sample_policy() -> Policy:
    """Create a sample policy for testing."""
    return Policy.default()


@pytest.fixture
def sample_finding() -> Finding:
    """Create a sample static finding for testing."""
    return Finding(
        rule_id="DB-001",
        rule_name="Unbounded Database Query",
        category=RuleCategory.DATABASE,
        severity=Severity.HIGH,
        confidence=Confidence.LIKELY,
        message="Database query retrieves potentially unlimited records without pagination/limit.",
        file_path="app.py",
        line_number=42,
        code_snippet="    results = db.session.query(Order).all()",
        evidence=[
            Evidence(
                type=EvidenceType.STATIC,
                source="static_analysis",
                description="Query call without limit clause",
                data={"query_method": "all", "model": "Order"},
                file_path="app.py",
                line_number=42,
            )
        ],
        recommendation="Add .limit() or pagination to prevent memory exhaustion under load.",
        potential_consequence="Memory exhaustion / excessive DB load at scale.",
    )


@pytest.fixture
def sample_measurement() -> Measurement:
    """Create a sample measurement for testing."""
    now = datetime.now(UTC)
    return Measurement(
        run_id="test-run-001",
        timestamp=now,
        workload_rps=100.0,
        request_metrics=RequestMetrics(
            timestamp=now,
            duration_seconds=300.0,
            total_requests=30000,
            successful_requests=29700,
            failed_requests=300,
            requests_per_second=100.0,
            error_rate=0.01,
            latency=LatencyDistribution(
                p50_ms=45.0,
                p75_ms=120.0,
                p90_ms=250.0,
                p95_ms=480.0,
                p99_ms=980.0,
                min_ms=5.0,
                max_ms=2500.0,
                mean_ms=95.0,
            ),
            status_codes={200: 29700, 500: 300},
        ),
        resource_metrics=ResourceMetrics(
            timestamp=now,
            cpu_percent=65.0,
            memory_mb=384.0,
            memory_percent=37.5,
            network_rx_bytes=1024000,
            network_tx_bytes=2048000,
            active_connections=45,
        ),
        database_metrics=DatabaseMetrics(
            timestamp=now,
            query_count=150000,
            query_rate_per_second=500.0,
            avg_query_latency_ms=12.0,
            max_query_latency_ms=450.0,
            active_connections=25,
            max_connections=100,
            connection_utilization=0.25,
            cache_hit_ratio=0.92,
        ),
    )


@pytest.fixture
def sample_verdict() -> Verdict:
    """Create a sample verdict for testing."""
    return Verdict(
        status=VerdictStatus.WARNING,
        category="p95_latency_ms",
        reason="p95 latency approaching threshold. Observed: 480ms, Threshold: ≤ 500ms",
        observed_value=480.0,
        workload_context="100 RPS for 5 minutes",
    )


@pytest.fixture
def sample_run(
    sample_target: Target,
    sample_environment: Environment,
    sample_policy: Policy,
    sample_finding: Finding,
    sample_measurement: Measurement,
    sample_verdict: Verdict,
) -> VerificationRun:
    """Create a complete sample verification run for testing."""
    now = datetime.now(UTC)
    return VerificationRun(
        target=sample_target,
        environment=sample_environment,
        policy=sample_policy,
        static_findings=[sample_finding],
        runtime_findings=[],
        measurements=[sample_measurement],
        verdicts=[sample_verdict],
        final_verdict=VerdictStatus.WARNING,
        metadata=RunMetadata(
            guardrail_version="0.1.0",
            start_time=now,
            end_time=now,
            duration_seconds=312.5,
            machine_info={"os": "linux", "arch": "x86_64", "cpu_count": "8"},
        ),
    )


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal temporary project for testing."""
    # Create a basic Python Flask project structure
    app_py = tmp_path / "app.py"
    app_py.write_text(
        """from flask import Flask, jsonify
import requests
import time

app = Flask(__name__)

# DB-001: Unbounded query
@app.route("/api/users")
def get_users():
    users = db.session.query(User).all()
    return jsonify(users)

# AMP-001: Tight polling
def poll_status():
    while True:
        response = requests.get("http://api.example.com/status")
        time.sleep(2)

# NET-001: Missing timeout
@app.route("/api/external")
def call_external():
    result = requests.get("http://api.example.com/data")
    return jsonify(result.json())

# CFG-001: Debug mode
if __name__ == "__main__":
    app.run(debug=True)
""",
        encoding="utf-8",
    )

    requirements = tmp_path / "requirements.txt"
    requirements.write_text("flask==3.0.0\nrequests==2.31.0\npsycopg2==2.9.9\n")

    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=postgresql://localhost:5432/mydb\nDEBUG=true\n")

    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        'FROM python:3.12-slim\nCOPY . /app\nWORKDIR /app\nRUN pip install -r requirements.txt\nCMD ["python", "app.py"]\n'
    )

    return tmp_path


@pytest.fixture
def tmp_js_project(tmp_path: Path) -> Path:
    """Create a minimal JavaScript project for testing."""
    index_js = tmp_path / "index.js"
    index_js.write_text(
        """const express = require("express");
const app = express();

// Missing timeout on fetch
app.get("/api/data", async (req, res) => {
    const response = await fetch("http://api.example.com/data");
    const data = await response.json();
    res.json(data);
});

// Polling with tight interval
setInterval(() => {
    fetch("http://api.example.com/status");
}, 2000);

app.listen(3000);
""",
        encoding="utf-8",
    )

    package_json = tmp_path / "package.json"
    package_json.write_text(
        '{"name": "test-app", "dependencies": {"express": "^4.18.0", "pg": "^8.11.0"}}'
    )

    return tmp_path
