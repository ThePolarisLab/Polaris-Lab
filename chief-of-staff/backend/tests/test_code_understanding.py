import pytest

from app.code_understanding.analyzer import CodeAnalysisError, PythonCodeAnalyzer


SOURCE = '''"""Example module."""
import os
from pathlib import Path as FilePath

MAX_RETRIES: int = 3


def helper(value: int) -> str:
    """Convert a value to text."""
    return str(value)


class Worker(BaseWorker):
    """Runs work."""

    @classmethod
    def build(cls, name):
        return cls(name)

    async def run(self, item):
        result = helper(item)
        await self.save(result)
        return result
'''


def test_analyzer_extracts_module_structure():
    result = PythonCodeAnalyzer().analyze(SOURCE, "worker.py")

    assert result["path"] == "worker.py"
    assert result["module_docstring"] == "Example module."
    assert result["metrics"] == {
        "lines": 23,
        "imports": 2,
        "functions": 1,
        "classes": 1,
        "methods": 2,
        "constants": 1,
    }


def test_analyzer_extracts_imports_and_constant():
    result = PythonCodeAnalyzer().analyze(SOURCE)

    assert result["imports"][0]["module"] == "os"
    assert result["imports"][1] == {
        "module": "pathlib",
        "name": "Path",
        "alias": "FilePath",
        "line": 3,
    }
    assert result["constants"][0]["name"] == "MAX_RETRIES"
    assert result["constants"][0]["annotation"] == "int"


def test_analyzer_extracts_classes_methods_and_calls():
    result = PythonCodeAnalyzer().analyze(SOURCE)
    worker = result["classes"][0]

    assert worker["name"] == "Worker"
    assert worker["bases"] == ["BaseWorker"]
    assert worker["methods"][0]["decorators"] == ["classmethod"]
    assert worker["methods"][1]["is_async"] is True
    assert result["call_graph"]["Worker.run"] == ["helper", "self.save"]


def test_analyzer_extracts_function_signature():
    result = PythonCodeAnalyzer().analyze(SOURCE)
    helper = result["functions"][0]

    assert helper["parameters"] == ["value"]
    assert helper["returns"] == "str"
    assert helper["docstring"] == "Convert a value to text."
    assert helper["calls"] == ["str"]


def test_explain_produces_plain_english_summary():
    explanation = PythonCodeAnalyzer().explain(SOURCE, "worker.py")

    assert "worker.py is a Python module" in explanation
    assert "Worker" in explanation
    assert "helper" in explanation
    assert "os" in explanation


def test_invalid_python_raises_analysis_error():
    with pytest.raises(CodeAnalysisError, match="Invalid Python syntax"):
        PythonCodeAnalyzer().analyze("def broken(:")


def test_source_size_limit_is_enforced():
    analyzer = PythonCodeAnalyzer()
    oversized = "x" * (analyzer.MAX_SOURCE_BYTES + 1)

    with pytest.raises(CodeAnalysisError, match="1 MB"):
        analyzer.analyze(oversized)
