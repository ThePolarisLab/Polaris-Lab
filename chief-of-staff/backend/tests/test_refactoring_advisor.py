from app.refactoring.advisor import PythonRefactoringAdvisor, RecommendationPolicy


def test_prioritizes_deterministic_refactoring_actions():
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

    result = PythonRefactoringAdvisor().analyze(source, "sample.py")

    assert result["path"] == "sample.py"
    assert result["metrics"]["total_recommendations"] >= 2
    assert result["recommendations"][0]["rank"] == 1
    assert result["recommendations"][0]["priority"] in {"high", "medium"}
    assert all(item["evidence"] for item in result["recommendations"])
    assert result["guardrails"]["modifies_source"] is False


def test_groups_matching_findings_into_one_action():
    source = """
def first():
    return 99

def second():
    return 99
"""

    result = PythonRefactoringAdvisor().analyze(source)
    magic = [item for item in result["recommendations"] if "magic_number" in item["smell_types"]]

    assert len(magic) == 1
    assert len(magic[0]["evidence"]) == 2
    assert magic[0]["target"] == "module"


def test_rejects_invalid_policy():
    try:
        RecommendationPolicy(high_priority_threshold=1, medium_priority_threshold=2)
    except ValueError as exc:
        assert "High priority threshold" in str(exc)
    else:
        raise AssertionError("Expected invalid recommendation policy to fail")


def test_returns_empty_plan_for_clean_source():
    result = PythonRefactoringAdvisor().analyze("def add(left, right):\n    return left + right\n")

    assert result["metrics"]["total_recommendations"] == 0
    assert result["recommendations"] == []
