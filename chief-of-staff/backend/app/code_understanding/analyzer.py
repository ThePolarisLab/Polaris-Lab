from __future__ import annotations

import ast
import os
from dataclasses import asdict, dataclass, field


class CodeAnalysisError(ValueError):
    """Raised when source code cannot be analyzed safely."""


@dataclass
class FunctionInfo:
    name: str
    line: int
    end_line: int | None
    parameters: list[str]
    decorators: list[str] = field(default_factory=list)
    returns: str | None = None
    docstring: str | None = None
    calls: list[str] = field(default_factory=list)
    is_async: bool = False


@dataclass
class ClassInfo:
    name: str
    line: int
    end_line: int | None
    bases: list[str]
    decorators: list[str] = field(default_factory=list)
    docstring: str | None = None
    methods: list[FunctionInfo] = field(default_factory=list)


class _CallCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        name = _expression_name(node.func)
        if name:
            self.calls.add(name)
        self.generic_visit(node)


class PythonCodeAnalyzer:
    """Extracts deterministic structural intelligence from Python source."""

    DEFAULT_MAX_SOURCE_BYTES = 1_000_000
    HARD_MAX_SOURCE_BYTES = 10_000_000
    MAX_SOURCE_BYTES_ENV = "POLARIS_CODE_ANALYSIS_MAX_BYTES"

    def __init__(self, max_source_bytes: int | None = None) -> None:
        self.max_source_bytes = self._resolve_max_source_bytes(max_source_bytes)

    @property
    def MAX_SOURCE_BYTES(self) -> int:
        """Backward-compatible access to the active per-instance limit."""
        return self.max_source_bytes

    def analyze(self, source: str, path: str = "<memory>") -> dict:
        source_bytes = len(source.encode("utf-8"))
        if source_bytes > self.max_source_bytes:
            raise CodeAnalysisError(
                "Source exceeds the configured analysis limit of "
                f"{self.max_source_bytes} bytes."
            )

        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError as exc:
            location = f"line {exc.lineno}" if exc.lineno else "unknown line"
            raise CodeAnalysisError(f"Invalid Python syntax at {location}: {exc.msg}") from exc

        imports: list[dict] = []
        functions: list[FunctionInfo] = []
        classes: list[ClassInfo] = []
        constants: list[dict] = []

        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(
                        {
                            "module": alias.name,
                            "name": None,
                            "alias": alias.asname,
                            "line": node.lineno,
                        }
                    )
            elif isinstance(node, ast.ImportFrom):
                module = "." * node.level + (node.module or "")
                for alias in node.names:
                    imports.append(
                        {
                            "module": module,
                            "name": alias.name,
                            "alias": alias.asname,
                            "line": node.lineno,
                        }
                    )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(self._function_info(node))
            elif isinstance(node, ast.ClassDef):
                classes.append(self._class_info(node))
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                constants.extend(self._constant_info(node))

        call_graph: dict[str, list[str]] = {}
        for function in functions:
            call_graph[function.name] = function.calls
        for class_info in classes:
            for method in class_info.methods:
                call_graph[f"{class_info.name}.{method.name}"] = method.calls

        summary = self._summary(path, imports, functions, classes, constants)
        return {
            "path": path,
            "language": "python",
            "module_docstring": ast.get_docstring(tree),
            "summary": summary,
            "imports": imports,
            "functions": [asdict(item) for item in functions],
            "classes": [asdict(item) for item in classes],
            "constants": constants,
            "call_graph": call_graph,
            "analysis_limit_bytes": self.max_source_bytes,
            "source_bytes": source_bytes,
            "metrics": {
                "lines": len(source.splitlines()),
                "imports": len(imports),
                "functions": len(functions),
                "classes": len(classes),
                "methods": sum(len(item.methods) for item in classes),
                "constants": len(constants),
            },
        }

    def explain(self, source: str, path: str = "<memory>") -> str:
        analysis = self.analyze(source, path)
        metrics = analysis["metrics"]
        parts = [analysis["summary"]]

        if analysis["classes"]:
            names = ", ".join(item["name"] for item in analysis["classes"])
            parts.append(f"It defines the following classes: {names}.")
        if analysis["functions"]:
            names = ", ".join(item["name"] for item in analysis["functions"])
            parts.append(f"Its module-level functions are: {names}.")
        if analysis["imports"]:
            modules = sorted({item["module"] for item in analysis["imports"]})
            parts.append(f"It depends directly on: {', '.join(modules)}.")
        if metrics["methods"]:
            parts.append(f"Across its classes, it contains {metrics['methods']} methods.")

        return " ".join(parts)

    @classmethod
    def _resolve_max_source_bytes(cls, explicit_limit: int | None) -> int:
        value = explicit_limit
        if value is None:
            raw = os.getenv(cls.MAX_SOURCE_BYTES_ENV, "").strip()
            if not raw:
                return cls.DEFAULT_MAX_SOURCE_BYTES
            try:
                value = int(raw)
            except ValueError as exc:
                raise CodeAnalysisError(
                    f"{cls.MAX_SOURCE_BYTES_ENV} must be a positive integer."
                ) from exc

        if isinstance(value, bool) or value <= 0:
            raise CodeAnalysisError("The analysis size limit must be a positive integer.")
        if value > cls.HARD_MAX_SOURCE_BYTES:
            raise CodeAnalysisError(
                "The analysis size limit cannot exceed "
                f"{cls.HARD_MAX_SOURCE_BYTES} bytes."
            )
        return value

    def _class_info(self, node: ast.ClassDef) -> ClassInfo:
        methods = [
            self._function_info(item)
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        return ClassInfo(
            name=node.name,
            line=node.lineno,
            end_line=getattr(node, "end_lineno", None),
            bases=[_expression_name(base) or ast.unparse(base) for base in node.bases],
            decorators=[_expression_name(item) or ast.unparse(item) for item in node.decorator_list],
            docstring=ast.get_docstring(node),
            methods=methods,
        )

    def _function_info(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionInfo:
        parameters = [argument.arg for argument in node.args.posonlyargs]
        parameters.extend(argument.arg for argument in node.args.args)
        if node.args.vararg:
            parameters.append(f"*{node.args.vararg.arg}")
        parameters.extend(argument.arg for argument in node.args.kwonlyargs)
        if node.args.kwarg:
            parameters.append(f"**{node.args.kwarg.arg}")

        collector = _CallCollector()
        collector.visit(node)

        return FunctionInfo(
            name=node.name,
            line=node.lineno,
            end_line=getattr(node, "end_lineno", None),
            parameters=parameters,
            decorators=[_expression_name(item) or ast.unparse(item) for item in node.decorator_list],
            returns=ast.unparse(node.returns) if node.returns else None,
            docstring=ast.get_docstring(node),
            calls=sorted(collector.calls),
            is_async=isinstance(node, ast.AsyncFunctionDef),
        )

    def _constant_info(self, node: ast.Assign | ast.AnnAssign) -> list[dict]:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        results: list[dict] = []
        for target in targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                results.append(
                    {
                        "name": target.id,
                        "line": node.lineno,
                        "annotation": (
                            ast.unparse(node.annotation)
                            if isinstance(node, ast.AnnAssign) and node.annotation
                            else None
                        ),
                    }
                )
        return results

    @staticmethod
    def _summary(path: str, imports: list[dict], functions: list[FunctionInfo], classes: list[ClassInfo], constants: list[dict]) -> str:
        return (
            f"{path} is a Python module with {len(classes)} classes, "
            f"{len(functions)} module-level functions, {len(imports)} imports, "
            f"and {len(constants)} named constants."
        )


def _expression_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _expression_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _expression_name(node.func)
    return None
