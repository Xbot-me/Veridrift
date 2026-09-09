from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from guardrail.cli.main import cli


def test_verify_cmd_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["verify", "--help"])
    assert result.exit_code == 0
    assert "Execute complete empirical runtime verification" in result.output
    assert "--stages" in result.output
    assert "--stage-duration" in result.output


def test_verify_cmd_runs_on_target(tmp_path: Path):
    # Create minimal server target
    app_file = tmp_path / "app.py"
    app_file.write_text(
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

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "verify",
            str(tmp_path),
            "--stages",
            "5,10",
            "--stage-duration",
            "0.5",
            "--endpoint",
            "/",
        ],
    )

    assert result.exit_code == 0
    assert "Guardrail Production Runtime Verification Engine" in result.output
    assert "Empirical Capacity Boundary" in result.output
    assert "SHA-256 Manifest" in result.output
