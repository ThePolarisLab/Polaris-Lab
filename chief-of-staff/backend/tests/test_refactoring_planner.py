import pytest

from app.refactoring.planner import PlanningPolicy, RefactoringExecutionPlanner


def test_generates_ordered_impact_plan():
    source = """
def transform(a, b, c, d, e, f):
    value = 3
    if a:
        if b:
            if c:
                if d:
                    if e:
                        return value
    return 4
"""

    result = RefactoringExecutionPlanner().analyze(source, "sample.py")

    assert result["path"] == "sample.py"
    assert result["metrics"]["total_steps"] >= 2
    assert [item["execution_order"] for item in result["execution_plan"]] == list(
        range(1, result["metrics"]["total_steps"] + 1)
    )
    assert all(item["impact"]["benefit_score"] > 0 for item in result["execution_plan"])
    assert all(item["rationale"] for item in result["execution_plan"])
    assert result["guardrails"]["modifies_source"] is False


def test_dependency_precedes_dependent_action():
    planner = RefactoringExecutionPlanner()
    plan = [
        {"action": "dependent", "dependencies": ["prerequisite"], "priority": "high", "line": 1, "impact": {"benefit_score": 8}},
        {"action": "prerequisite", "dependencies": [], "priority": "low", "line": 2, "impact": {"benefit_score": 2}},
    ]

    ordered = planner._topological_order(plan)

    assert [item["action"] for item in ordered] == ["prerequisite", "dependent"]


def test_rejects_missing_dependency():
    with pytest.raises(ValueError, match="Missing refactoring dependencies"):
        RefactoringExecutionPlanner._validate_dependencies(
            [{"action": "dependent", "dependencies": ["missing"]}]
        )


def test_rejects_circular_dependencies():
    plan = [
        {"action": "first", "dependencies": ["second"], "priority": "high", "line": 1, "impact": {"benefit_score": 8}},
        {"action": "second", "dependencies": ["first"], "priority": "medium", "line": 2, "impact": {"benefit_score": 5}},
    ]

    with pytest.raises(ValueError, match="Circular refactoring dependency"):
        RefactoringExecutionPlanner._topological_order(plan)


def test_empty_source_returns_empty_plan():
    result = RefactoringExecutionPlanner().analyze("def add(left, right):\n    return left + right\n")

    assert result["metrics"]["total_steps"] == 0
    assert result["execution_plan"] == []


def test_rejects_invalid_planning_policy():
    with pytest.raises(ValueError, match="High risk threshold"):
        PlanningPolicy(high_risk_threshold=2, medium_risk_threshold=4)
