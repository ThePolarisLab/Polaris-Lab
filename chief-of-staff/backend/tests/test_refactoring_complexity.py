import pytest

from app.refactoring.complexity import (
    ComplexityAnalysisError,
    ComplexityThresholds,
    PythonComplexityAnalyzer,
)


def test_simple_function_has_baseline_complexity():
    result = PythonComplexityAnalyzer().analyze("def greet(name):\n    return f'Hi {name}'\n")
    function = result["functions"][0]

    assert function["qualified_name"] == "greet"
    assert function["complexity"] == 1
    assert function["rating"] == "Excellent"
    assert function["parameters"] == 1
    assert function["returns"] == 1
    assert function["recommendations"] == []


def test_branch_loop_boolean_and_exception_increase_complexity():
    source = '''def process(items, enabled=True):
    total = 0
    try:
        for item in items:
            if enabled and item > 0:
                total += item
    except ValueError:
        return 0
    return total
'''
    function = PythonComplexityAnalyzer().analyze(source)["functions"][0]

    assert function["complexity"] == 5
    assert function["branches"] == 2
    assert function["loops"] == 1
    assert function["try_blocks"] == 1
    assert function["returns"] == 2
    assert function["maximum_nesting"] >= 3


def test_methods_async_and_match_are_reported():
    source = '''class Worker:
    async def run(self, value):
        await self.save(value)
        match value:
            case 0:
                return "zero"
            case _:
                return "other"
'''
    result = PythonComplexityAnalyzer().analyze(source)
    method = result["functions"][0]

    assert result["metrics"]["methods"] == 1
    assert method["qualified_name"] == "Worker.run"
    assert method["class_name"] == "Worker"
    assert method["is_async"] is True
    assert method["match_statements"] == 1
    assert method["async_constructs"] == 2
    assert method["complexity"] == 3


def test_recommendations_are_deterministic_and_configurable():
    source = '''def crowded(a, b, c):
    if a:
        if b:
            return c
    return None
'''
    thresholds = ComplexityThresholds(
        moderate=2,
        high=3,
        critical=5,
        max_nesting=1,
        max_parameters=2,
        max_lines=4,
    )
    function = PythonComplexityAnalyzer(thresholds).analyze(source)["functions"][0]
    recommendation_types = {item["type"] for item in function["recommendations"]}

    assert function["rating"] == "High"
    assert recommendation_types == {
        "extract_method",
        "guard_clauses",
        "parameter_object",
        "split_function",
    }


def test_summary_orders_most_complex_callable_first():
    source = '''def simple():
    return 1


def complex_value(value):
    if value:
        for item in value:
            if item:
                return item
    return None
'''
    result = PythonComplexityAnalyzer().analyze(source)

    assert result["functions"][0]["name"] == "complex_value"
    assert result["metrics"]["total_callables"] == 2
    assert result["metrics"]["maximum_complexity"] == 4
    assert result["metrics"]["average_complexity"] == 2.5


def test_invalid_python_raises_clear_error():
    with pytest.raises(ComplexityAnalysisError, match="Invalid Python syntax"):
        PythonComplexityAnalyzer().analyze("def broken(:")


@pytest.mark.parametrize(
    "thresholds",
    [
        {"moderate": 0},
        {"moderate": 10, "high": 9},
        {"high": 20, "critical": 20},
    ],
)
def test_invalid_thresholds_are_rejected(thresholds):
    with pytest.raises(ComplexityAnalysisError):
        ComplexityThresholds(**thresholds)
