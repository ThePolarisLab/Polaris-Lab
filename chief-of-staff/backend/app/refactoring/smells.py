"""Deterministic Python code-smell detection built on the standard AST."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any

from app.refactoring.complexity import ComplexityAnalysisError, PythonComplexityAnalyzer


@dataclass(frozen=True)
class CodeSmellThresholds:
    """Configurable thresholds for the first code-smell detector increment."""

    long_method_lines: int = 50
    deep_nesting: int = 4
    long_parameter_list: int = 5
    too_many_locals: int = 12
    too_many_returns: int = 5
    large_class_methods: int = 12
    large_class_lines: int = 300

    def __post_init__(self) -> None:
        if any(value < 1 for value in self.__dict__.values()):
            raise ComplexityAnalysisError("Code-smell thresholds must be positive integers.")


class PythonCodeSmellDetector:
    """Find explainable maintainability risks without executing source code."""

    _IGNORED_MAGIC_NUMBERS = {-1, 0, 1, 2}

    def __init__(self, thresholds: CodeSmellThresholds | None = None) -> None:
        self.thresholds = thresholds or CodeSmellThresholds()

    def analyze(self, source: str, path: str = "<memory>") -> dict[str, Any]:
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError as exc:
            message = f"Invalid Python syntax at line {exc.lineno}: {exc.msg}"
            raise ComplexityAnalysisError(message) from exc

        complexity = PythonComplexityAnalyzer().analyze(source, path)
        findings: list[dict[str, Any]] = []

        for function in complexity["functions"]:
            findings.extend(self._function_findings(function))

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                findings.extend(self._class_findings(node))
            elif isinstance(node, ast.Constant):
                finding = self._magic_number_finding(node)
                if finding is not None:
                    findings.append(finding)

        findings.sort(
            key=lambda item: (
                item["line"],
                item["type"],
                item.get("qualified_name", ""),
            )
        )
        counts: dict[str, int] = {}
        severities = {"low": 0, "medium": 0, "high": 0}
        for finding in findings:
            counts[finding["type"]] = counts.get(finding["type"], 0) + 1
            severities[finding["severity"]] += 1

        return {
            "path": path,
            "metrics": {
                "total_findings": len(findings),
                "by_type": counts,
                "by_severity": severities,
            },
            "thresholds": self.thresholds.__dict__,
            "findings": findings,
            "scope": {
                "implemented": [
                    "long_method",
                    "deep_nesting",
                    "long_parameter_list",
                    "too_many_locals",
                    "too_many_returns",
                    "large_class",
                    "magic_number",
                ],
                "deferred": ["duplicate_code", "dead_code", "feature_envy"],
            },
        }

    def _function_findings(self, function: dict[str, Any]) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        checks = (
            (
                "long_method",
                function["lines"],
                self.thresholds.long_method_lines,
                "Split the callable into smaller single-purpose units.",
            ),
            (
                "deep_nesting",
                function["maximum_nesting"],
                self.thresholds.deep_nesting,
                "Use guard clauses or extract nested branches.",
            ),
            (
                "long_parameter_list",
                function["parameters"],
                self.thresholds.long_parameter_list,
                "Group cohesive arguments into a parameter object.",
            ),
            (
                "too_many_locals",
                function["local_variables"],
                self.thresholds.too_many_locals,
                "Extract cohesive calculations and reduce local state.",
            ),
            (
                "too_many_returns",
                function["returns"],
                self.thresholds.too_many_returns,
                "Simplify control flow or consolidate return paths.",
            ),
        )
        for smell_type, value, threshold, recommendation in checks:
            if value > threshold:
                findings.append(
                    self._finding(
                        smell_type=smell_type,
                        line=function["line"],
                        end_line=function["end_line"],
                        qualified_name=function["qualified_name"],
                        value=value,
                        threshold=threshold,
                        recommendation=recommendation,
                    )
                )
        return findings

    def _class_findings(self, node: ast.ClassDef) -> list[dict[str, Any]]:
        methods = [
            child
            for child in node.body
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        end_line = getattr(node, "end_lineno", node.lineno)
        lines = max(1, end_line - node.lineno + 1)
        if (
            len(methods) <= self.thresholds.large_class_methods
            and lines <= self.thresholds.large_class_lines
        ):
            return []
        return [
            {
                "type": "large_class",
                "severity": "high" if len(methods) > self.thresholds.large_class_methods else "medium",
                "confidence": 0.94,
                "line": node.lineno,
                "end_line": end_line,
                "qualified_name": node.name,
                "evidence": {
                    "methods": len(methods),
                    "method_threshold": self.thresholds.large_class_methods,
                    "lines": lines,
                    "line_threshold": self.thresholds.large_class_lines,
                },
                "recommendation": "Split responsibilities into smaller cohesive classes.",
            }
        ]

    def _magic_number_finding(self, node: ast.Constant) -> dict[str, Any] | None:
        value = node.value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if value in self._IGNORED_MAGIC_NUMBERS:
            return None
        return {
            "type": "magic_number",
            "severity": "low",
            "confidence": 0.75,
            "line": node.lineno,
            "end_line": getattr(node, "end_lineno", node.lineno),
            "qualified_name": None,
            "evidence": {"value": value},
            "recommendation": "Replace unexplained numeric literals with a named constant when domain meaning exists.",
        }

    @staticmethod
    def _finding(
        *,
        smell_type: str,
        line: int,
        end_line: int,
        qualified_name: str,
        value: int,
        threshold: int,
        recommendation: str,
    ) -> dict[str, Any]:
        ratio = value / threshold
        severity = "high" if ratio >= 2 else "medium"
        confidence = 0.96 if ratio >= 1.5 else 0.9
        return {
            "type": smell_type,
            "severity": severity,
            "confidence": confidence,
            "line": line,
            "end_line": end_line,
            "qualified_name": qualified_name,
            "evidence": {"value": value, "threshold": threshold},
            "recommendation": recommendation,
        }
