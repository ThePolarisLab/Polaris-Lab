"""Deterministic Python complexity analysis built on the standard AST."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any


class ComplexityAnalysisError(ValueError):
    """Raised when source cannot be analyzed safely."""


@dataclass(frozen=True)
class ComplexityThresholds:
    """Configurable thresholds used to classify and advise on functions."""

    moderate: int = 11
    high: int = 16
    critical: int = 21
    max_nesting: int = 4
    max_parameters: int = 5
    max_lines: int = 50

    def __post_init__(self) -> None:
        values = (
            self.moderate,
            self.high,
            self.critical,
            self.max_nesting,
            self.max_parameters,
            self.max_lines,
        )
        if any(value < 1 for value in values):
            raise ComplexityAnalysisError("Complexity thresholds must be positive integers.")
        if not self.moderate < self.high < self.critical:
            raise ComplexityAnalysisError(
                "Complexity rating thresholds must increase from moderate to critical."
            )


@dataclass
class _FunctionState:
    complexity: int = 1
    branches: int = 0
    loops: int = 0
    returns: int = 0
    try_blocks: int = 0
    match_statements: int = 0
    async_constructs: int = 0
    max_nesting: int = 0
    local_names: set[str] = field(default_factory=set)


class _FunctionMetricsVisitor(ast.NodeVisitor):
    """Measure one function while excluding nested function definitions."""

    def __init__(self) -> None:
        self.state = _FunctionState()
        self._nesting = 0
        self._root: ast.AST | None = None

    def analyze(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> _FunctionState:
        self._root = node
        if isinstance(node, ast.AsyncFunctionDef):
            self.state.async_constructs += 1
        for statement in node.body:
            self.visit(statement)
        return self.state

    def _nested(self, node: ast.AST) -> None:
        self._nesting += 1
        self.state.max_nesting = max(self.state.max_nesting, self._nesting)
        self.generic_visit(node)
        self._nesting -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node is self._root:
            self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if node is self._root:
            self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_If(self, node: ast.If) -> None:
        self.state.complexity += 1
        self.state.branches += 1
        self._nested(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.state.complexity += 1
        self.state.branches += 1
        self._nested(node)

    def visit_For(self, node: ast.For) -> None:
        self.state.complexity += 1
        self.state.loops += 1
        self._nested(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.state.complexity += 1
        self.state.loops += 1
        self.state.async_constructs += 1
        self._nested(node)

    def visit_While(self, node: ast.While) -> None:
        self.state.complexity += 1
        self.state.loops += 1
        self._nested(node)

    def visit_Try(self, node: ast.Try) -> None:
        self.state.try_blocks += 1
        self._nested(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.state.complexity += 1
        self.state.branches += 1
        self._nested(node)

    def visit_Match(self, node: ast.Match) -> None:
        self.state.match_statements += 1
        self.state.branches += len(node.cases)
        self.state.complexity += len(node.cases)
        self._nested(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.state.complexity += max(0, len(node.values) - 1)
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self.state.complexity += 1 + len(node.ifs)
        self.state.loops += 1
        self._nested(node)

    def visit_Return(self, node: ast.Return) -> None:
        self.state.returns += 1
        self.generic_visit(node)

    def visit_Await(self, node: ast.Await) -> None:
        self.state.async_constructs += 1
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self.state.async_constructs += 1
        self._nested(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self.state.local_names.add(node.id)


class PythonComplexityAnalyzer:
    """Analyze function and method complexity without executing source code."""

    def __init__(self, thresholds: ComplexityThresholds | None = None) -> None:
        self.thresholds = thresholds or ComplexityThresholds()

    def analyze(self, source: str, path: str = "<memory>") -> dict[str, Any]:
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError as exc:
            message = f"Invalid Python syntax at line {exc.lineno}: {exc.msg}"
            raise ComplexityAnalysisError(message) from exc

        functions: list[dict[str, Any]] = []
        self._collect(tree.body, functions, class_name=None)
        functions.sort(key=lambda item: (-item["complexity"], item["qualified_name"]))

        ratings = {name: 0 for name in ("excellent", "good", "moderate", "high", "critical")}
        for function in functions:
            ratings[function["rating"].lower()] += 1

        return {
            "path": path,
            "metrics": {
                "functions": sum(1 for item in functions if item["class_name"] is None),
                "methods": sum(1 for item in functions if item["class_name"] is not None),
                "total_callables": len(functions),
                "average_complexity": round(
                    sum(item["complexity"] for item in functions) / len(functions), 2
                )
                if functions
                else 0.0,
                "maximum_complexity": max(
                    (item["complexity"] for item in functions), default=0
                ),
                "ratings": ratings,
            },
            "thresholds": {
                "moderate": self.thresholds.moderate,
                "high": self.thresholds.high,
                "critical": self.thresholds.critical,
                "max_nesting": self.thresholds.max_nesting,
                "max_parameters": self.thresholds.max_parameters,
                "max_lines": self.thresholds.max_lines,
            },
            "functions": functions,
        }

    def _collect(
        self,
        statements: list[ast.stmt],
        results: list[dict[str, Any]],
        class_name: str | None,
    ) -> None:
        for node in statements:
            if isinstance(node, ast.ClassDef):
                self._collect(node.body, results, class_name=node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                results.append(self._measure(node, class_name))
                self._collect(node.body, results, class_name=class_name)

    def _measure(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        class_name: str | None,
    ) -> dict[str, Any]:
        state = _FunctionMetricsVisitor().analyze(node)
        parameters = self._parameter_count(node.args)
        end_line = getattr(node, "end_lineno", node.lineno)
        lines = max(1, end_line - node.lineno + 1)
        rating = self._rating(state.complexity)
        qualified_name = f"{class_name}.{node.name}" if class_name else node.name
        recommendations = self._recommend(
            complexity=state.complexity,
            nesting=state.max_nesting,
            parameters=parameters,
            lines=lines,
        )
        return {
            "name": node.name,
            "qualified_name": qualified_name,
            "class_name": class_name,
            "line": node.lineno,
            "end_line": end_line,
            "lines": lines,
            "is_async": isinstance(node, ast.AsyncFunctionDef),
            "parameters": parameters,
            "local_variables": len(state.local_names),
            "complexity": state.complexity,
            "rating": rating,
            "maximum_nesting": state.max_nesting,
            "branches": state.branches,
            "loops": state.loops,
            "returns": state.returns,
            "try_blocks": state.try_blocks,
            "match_statements": state.match_statements,
            "async_constructs": state.async_constructs,
            "recommendations": recommendations,
        }

    @staticmethod
    def _parameter_count(arguments: ast.arguments) -> int:
        return (
            len(arguments.posonlyargs)
            + len(arguments.args)
            + len(arguments.kwonlyargs)
            + (1 if arguments.vararg else 0)
            + (1 if arguments.kwarg else 0)
        )

    def _rating(self, complexity: int) -> str:
        if complexity >= self.thresholds.critical:
            return "Critical"
        if complexity >= self.thresholds.high:
            return "High"
        if complexity >= self.thresholds.moderate:
            return "Moderate"
        if complexity >= 6:
            return "Good"
        return "Excellent"

    def _recommend(
        self, complexity: int, nesting: int, parameters: int, lines: int
    ) -> list[dict[str, Any]]:
        recommendations: list[dict[str, Any]] = []
        if complexity >= self.thresholds.high:
            recommendations.append(
                {
                    "type": "extract_method",
                    "message": "Extract cohesive branches into smaller functions.",
                    "confidence": 0.95,
                }
            )
        if nesting > self.thresholds.max_nesting:
            recommendations.append(
                {
                    "type": "guard_clauses",
                    "message": "Use guard clauses to reduce nesting depth.",
                    "confidence": 0.93,
                }
            )
        if parameters > self.thresholds.max_parameters:
            recommendations.append(
                {
                    "type": "parameter_object",
                    "message": "Group related arguments in a parameter object or dataclass.",
                    "confidence": 0.9,
                }
            )
        if lines > self.thresholds.max_lines:
            recommendations.append(
                {
                    "type": "split_function",
                    "message": "Split the callable into smaller single-purpose units.",
                    "confidence": 0.88,
                }
            )
        return recommendations
