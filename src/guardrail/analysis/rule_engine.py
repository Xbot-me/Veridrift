from __future__ import annotations

from guardrail.models.base import RuleCategory
from guardrail.models.rule import Finding

from .rules.amplification import (
    AMP001_TightPollingInterval,
    AMP002_RetryWithoutBackoff,
    AMP003_RecursiveNestedHttpRequests,
)
from .rules.base import AnalysisContext, BaseRule
from .rules.concurrency import CONC001_UnboundedWorkerCreation
from .rules.configuration import CFG001_DebugModeEnabled, CFG002_MissingResourceLimits

# Import all rule classes
from .rules.database import (
    DB001_UnboundedDatabaseQuery,
    DB002_QueryInsideLoop,
    DB003_SelectStarUsage,
    DB004_LargeOffsetPagination,
)
from .rules.network import NET001_MissingTimeoutOnHttpRequest, NET002_UnboundedRetryLoop
from .rules.reliability import REL001_NoCircuitBreaker
from .rules.resource import RES001_UnclosedFileConnection, RES002_UnboundedInMemoryCollection


class RuleEngine:
    def __init__(self, register_builtins: bool = True):
        self._rules: list[BaseRule] = []
        if register_builtins:
            self.register_builtin_rules()

    def register_rule(self, rule: BaseRule) -> None:
        if not any(r.rule_definition.id == rule.rule_definition.id for r in self._rules):
            self._rules.append(rule)

    def register_builtin_rules(self) -> None:
        builtins = [
            DB001_UnboundedDatabaseQuery(),
            DB002_QueryInsideLoop(),
            DB003_SelectStarUsage(),
            DB004_LargeOffsetPagination(),
            AMP001_TightPollingInterval(),
            AMP002_RetryWithoutBackoff(),
            AMP003_RecursiveNestedHttpRequests(),
            NET001_MissingTimeoutOnHttpRequest(),
            NET002_UnboundedRetryLoop(),
            RES001_UnclosedFileConnection(),
            RES002_UnboundedInMemoryCollection(),
            CONC001_UnboundedWorkerCreation(),
            CFG001_DebugModeEnabled(),
            CFG002_MissingResourceLimits(),
            REL001_NoCircuitBreaker(),
        ]
        for rule in builtins:
            self.register_rule(rule)

    def get_rules(
        self, category: RuleCategory | None = None, severity=None, language=None
    ) -> list[BaseRule]:
        filtered = self._rules
        if category:
            filtered = [r for r in filtered if r.rule_definition.category == category]
        if severity:
            filtered = [r for r in filtered if r.rule_definition.severity == severity]
        # Language filtering could be implemented via a rule metadata attribute if added
        return filtered

    def evaluate_all(self, context: AnalysisContext) -> list[Finding]:
        all_findings = []
        for rule in self._rules:
            findings = rule.evaluate(context)
            all_findings.extend(findings)
        return all_findings

    def evaluate_category(self, category: RuleCategory, context: AnalysisContext) -> list[Finding]:
        findings = []
        for rule in self.get_rules(category=category):
            findings.extend(rule.evaluate(context))
        return findings
