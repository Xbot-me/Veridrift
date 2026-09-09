"""Integration tests for the Guardrail CLI."""

from __future__ import annotations

import os
from pathlib import Path

from click.testing import CliRunner

from guardrail.cli.main import cli


class TestCLIIntegration:
    """Test all CLI commands through Click's CliRunner."""

    def test_cli_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Production Verification Engine" in result.output
        assert "inspect" in result.output
        assert "analyze" in result.output
        assert "run" in result.output

    def test_cli_version(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_init_command(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0
            assert os.path.exists("guardrail.yaml")
            assert os.path.exists("policy.yaml")
            assert os.path.isdir(".guardrail")

    def test_inspect_command(self, tmp_project: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["inspect", str(tmp_project)])
        assert result.exit_code == 0
        assert "Python" in result.output
        assert "Target Information" in result.output

    def test_analyze_command(self, tmp_project: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["analyze", str(tmp_project)])
        assert result.exit_code == 0
        assert "Static Analysis Findings" in result.output
        assert "DB-001" in result.output or "NET-001" in result.output

    def test_analyze_filter_severity(self, tmp_project: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["analyze", str(tmp_project), "--severity", "HIGH"])
        assert result.exit_code == 0
        assert "Static Analysis Findings" in result.output

    def test_run_no_runtime_does_not_raise_and_is_inconclusive(self) -> None:
        """guardrail run must never surface NotImplementedError; without a
        usable runtime it reports INCONCLUSIVE with an explicit reason."""
        runner = CliRunner()
        demo_app = Path(__file__).resolve().parents[2] / "examples" / "demo_app"
        result = runner.invoke(cli, ["run", str(demo_app)])
        assert result.exit_code == 0, f"run failed: {result.output}"
        assert "NotImplementedError" not in result.output
        assert "INCONCLUSIVE" in result.output
        assert "Runtime available" in result.output or "No usable runtime" in result.output
        assert "Saved to evidence store" in result.output

    def test_full_lifecycle_run_and_report_and_compare(self, tmp_project: Path) -> None:
        runner = CliRunner()

        # 1. Run first verification
        res1 = runner.invoke(cli, ["run", str(tmp_project)])
        assert res1.exit_code == 0
        assert "Saved to evidence store" in res1.output

        import re

        m1 = re.search(r"([a-f0-9]{32})", res1.output)
        assert m1 is not None, f"Could not find run ID in output: {res1.output}"
        run_id_1 = m1.group(1)

        # 2. Run second verification
        res2 = runner.invoke(cli, ["run", str(tmp_project)])
        assert res2.exit_code == 0
        m2 = re.search(r"([a-f0-9]{32})", res2.output)
        assert m2 is not None
        run_id_2 = m2.group(1)

        # 3. Report command
        rep_res = runner.invoke(cli, ["report", run_id_1])
        assert rep_res.exit_code == 0
        assert "Production Verification Report" in rep_res.output

        # 4. Report JSON format
        rep_json = runner.invoke(cli, ["report", run_id_1, "--format", "json"])
        assert rep_json.exit_code == 0
        assert '"schema_version"' in rep_json.output or '"final_verdict"' in rep_json.output

        # 5. Compare command
        comp_res = runner.invoke(cli, ["compare", run_id_1, run_id_2])
        assert comp_res.exit_code == 0
        assert "Run Comparison" in comp_res.output
        assert "Verdict" in comp_res.output
