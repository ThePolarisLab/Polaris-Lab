import pytest

from app.refactoring.complexity import ComplexityAnalysisError
from app.refactoring.smells import CodeSmellThresholds, PythonCodeSmellDetector


def test_clean_function_has_no_findings():
    result = PythonCodeSmellDetector().analyze(
        "def greet(name):\n    return f'Hi {name}'\n"
    )

    assert result["metrics"]["total_findings"] == 0
    assert result["findings"] == []


def test_function_smells_are_evidence_backed_and_deterministic():
    source = '''def crowded(a, b, c):
    first = 10
    second = 20
    third = 30
    if a:
        if b:
            if c:
                return first
    return second
'''
    thresholds = CodeSmellThresholds(
        long_method_lines=6,
        deep_nesting=2,
        long_parameter_list=2,
        too_many_locals=2,
        too_many_returns=1,
        large_class_methods=5,
        large_class_lines=100,
    )
    result = PythonCodeSmellDetector(thresholds).analyze(source, "sample.py")
    finding_types = {item["type"] for item in result["findings"]}

    assert {
        "long_method",
        "deep_nesting",
        "long_parameter_list",
        "too_many_locals",
        "too_many_returns",
        "magic_number",
    }.issubset(finding_types)
    assert result["path"] == "sample.py"
    assert all("evidence" in item for item in result["findings"])
    assert all("recommendation" in item for item in result["findings"])


def test_large_class_is_reported():
    source = '''class Worker:
    def one(self):
        return 1

    def two(self):
        return 2

    def three(self):
        return 3
'''
    thresholds = CodeSmellThresholds(large_class_methods=2)
    result = PythonCodeSmellDetector(thresholds).analyze(source)
    large_class = next(item for item in result["findings"] if item["type"] == "large_class")

    assert large_class["qualified_name"] == "Worker"
    assert large_class["evidence"]["methods"] == 3


def test_common_control_values_are_not_magic_numbers():
    source = '''def normalize(value):
    if value in (-1, 0, 1, 2):
        return value
    return 42
'''
    result = PythonCodeSmellDetector().analyze(source)
    magic_values = [
        item["evidence"]["value"]
        for item in result["findings"]
        if item["type"] == "magic_number"
    ]

    assert magic_values == [42]


def test_invalid_python_raises_clear_error():
    with pytest.raises(ComplexityAnalysisError, match="Invalid Python syntax"):
        PythonCodeSmellDetector().analyze("def broken(:")


@pytest.mark.parametrize("field", ["long_method_lines", "large_class_methods"])
def test_invalid_thresholds_are_rejected(field):
    with pytest.raises(ComplexityAnalysisError):
        CodeSmellThresholds(**{field: 0})
