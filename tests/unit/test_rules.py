"""Unit tests for static analysis rules."""

from __future__ import annotations

from pathlib import Path

from guardrail.models.base import Severity


class TestDatabaseRules:
    """Test database-related static analysis rules."""

    def test_db001_unbounded_query(self, tmp_project: Path) -> None:
        """DB-001: Should detect .all() without limit."""
        from guardrail.analysis.engine import AnalysisEngine

        engine = AnalysisEngine(tmp_project)
        engine.register_builtin_parsers()
        result = engine.analyze(languages=["python"])

        db_findings = [f for f in result.findings if f.rule_id == "DB-001"]
        assert len(db_findings) > 0, "Should detect unbounded query (.all())"
        finding = db_findings[0]
        assert finding.severity == Severity.HIGH
        assert finding.file_path is not None
        assert finding.line_number is not None

    def test_db001_has_evidence(self, tmp_project: Path) -> None:
        """DB-001 findings should include code evidence."""
        from guardrail.analysis.engine import AnalysisEngine

        engine = AnalysisEngine(tmp_project)
        engine.register_builtin_parsers()
        result = engine.analyze(languages=["python"])

        db_findings = [f for f in result.findings if f.rule_id == "DB-001"]
        if db_findings:
            finding = db_findings[0]
            assert finding.code_snippet is not None or len(finding.evidence) > 0


class TestNetworkRules:
    """Test network-related static analysis rules."""

    def test_net001_missing_timeout(self, tmp_project: Path) -> None:
        """NET-001: Should detect requests.get without timeout."""
        from guardrail.analysis.engine import AnalysisEngine

        engine = AnalysisEngine(tmp_project)
        engine.register_builtin_parsers()
        result = engine.analyze(languages=["python"])

        net_findings = [f for f in result.findings if f.rule_id == "NET-001"]
        assert len(net_findings) > 0, "Should detect HTTP request without timeout"


class TestAmplificationRules:
    """Test traffic amplification rules."""

    def test_amp001_tight_polling(self, tmp_project: Path) -> None:
        """AMP-001: Should detect tight polling intervals."""
        from guardrail.analysis.engine import AnalysisEngine

        engine = AnalysisEngine(tmp_project)
        engine.register_builtin_parsers()
        result = engine.analyze(languages=["python"])

        amp_findings = [f for f in result.findings if f.rule_id == "AMP-001"]
        # time.sleep(2) is a tight interval
        assert len(amp_findings) > 0, "Should detect tight polling interval"


class TestConfigurationRules:
    """Test configuration rules."""

    def test_cfg001_debug_mode(self, tmp_project: Path) -> None:
        """CFG-001: Should detect debug=True."""
        from guardrail.analysis.engine import AnalysisEngine

        engine = AnalysisEngine(tmp_project)
        engine.register_builtin_parsers()
        result = engine.analyze(languages=["python"])

        cfg_findings = [f for f in result.findings if f.rule_id == "CFG-001"]
        assert len(cfg_findings) > 0, "Should detect debug mode enabled"


class TestAnalysisEngine:
    """Test the analysis engine orchestration."""

    def test_analyze_returns_result(self, tmp_project: Path) -> None:
        from guardrail.analysis.engine import AnalysisEngine

        engine = AnalysisEngine(tmp_project)
        engine.register_builtin_parsers()
        result = engine.analyze()

        assert result.files_analyzed > 0
        assert result.rules_evaluated > 0
        assert result.duration_seconds >= 0

    def test_findings_have_required_fields(self, tmp_project: Path) -> None:
        from guardrail.analysis.engine import AnalysisEngine

        engine = AnalysisEngine(tmp_project)
        engine.register_builtin_parsers()
        result = engine.analyze()

        for finding in result.findings:
            assert finding.rule_id, "Finding must have a rule_id"
            assert finding.severity, "Finding must have a severity"
            assert finding.confidence, "Finding must have a confidence"
            assert finding.message, "Finding must have a message"

    def test_empty_project_no_crash(self, tmp_path: Path) -> None:
        """Analysis engine should not crash on empty projects."""
        from guardrail.analysis.engine import AnalysisEngine

        engine = AnalysisEngine(tmp_path)
        engine.register_builtin_parsers()
        result = engine.analyze()

        assert result.files_analyzed == 0
        assert len(result.findings) == 0
