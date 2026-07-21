"""Deterministic impact analysis and execution planning for refactoring work."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.refactoring.advisor import PythonRefactoringAdvisor


@dataclass(frozen=True)
class PlanningPolicy:
    """Weights used to estimate benefit, effort, risk, and execution order."""

    high_priority_benefit: int = 8
    medium_priority_benefit: int = 5
    low_priority_benefit: int = 2
    evidence_effort_weight: int = 1
    high_risk_threshold: int = 7
    medium_risk_threshold: int = 4

    def __post_init__(self) -> None:
        values = self.__dict__.values()
        if any(not isinstance(value, int) or value < 0 for value in values):
            raise ValueError("Planning policy values must be non-negative integers.")
        if self.high_risk_threshold < self.medium_risk_threshold:
            raise ValueError("High risk threshold must be at least the medium threshold.")


class RefactoringExecutionPlanner:
    """Convert recommendations into an ordered, explainable execution plan."""

    _ACTION_DEPENDENCIES = {
        "Split this function into smaller focused functions.": [
            "Extract nested logic into named helper functions or guard clauses."
        ],
        "Introduce a parameter object or cohesive data structure.": [
            "Split this function into smaller focused functions."
        ],
    }

    def __init__(self, policy: PlanningPolicy | None = None) -> None:
        self.policy = policy or PlanningPolicy()

    def analyze(self, source: str, path: str = "<memory>") -> dict[str, Any]:
        advisor = PythonRefactoringAdvisor().analyze(source, path)
        recommendations = advisor["recommendations"]
        actions = {item["action"] for item in recommendations}

        plan = [self._plan_item(item, actions) for item in recommendations]
        self._validate_dependencies(plan)
        ordered = self._topological_order(plan)

        for index, item in enumerate(ordered, start=1):
            item["execution_order"] = index

        total_benefit = sum(item["impact"]["benefit_score"] for item in ordered)
        total_effort = sum(item["impact"]["effort_points"] for item in ordered)
        expected_complexity_reduction = min(60, sum(item["impact"]["complexity_reduction_percent"] for item in ordered))
        expected_debt_reduction = min(70, sum(item["impact"]["technical_debt_reduction_percent"] for item in ordered))

        return {
            "path": path,
            "metrics": {
                "total_steps": len(ordered),
                "total_benefit_score": total_benefit,
                "total_effort_points": total_effort,
                "expected_complexity_reduction_percent": expected_complexity_reduction,
                "expected_technical_debt_reduction_percent": expected_debt_reduction,
            },
            "policy": self.policy.__dict__,
            "execution_plan": ordered,
            "source_recommendations": advisor["metrics"],
            "guardrails": {
                "deterministic": True,
                "executes_source": False,
                "modifies_source": False,
                "estimates_are_directional": True,
            },
        }

    def _plan_item(self, recommendation: dict[str, Any], available_actions: set[str]) -> dict[str, Any]:
        priority = recommendation["priority"]
        evidence_count = len(recommendation["evidence"])
        benefit = {
            "high": self.policy.high_priority_benefit,
            "medium": self.policy.medium_priority_benefit,
            "low": self.policy.low_priority_benefit,
        }[priority] + min(3, evidence_count - 1)
        effort = max(1, evidence_count * self.policy.evidence_effort_weight + len(recommendation["smell_types"]))
        risk_score = min(10, effort + (2 if priority == "high" else 1 if priority == "medium" else 0))
        dependencies = [
            action for action in self._ACTION_DEPENDENCIES.get(recommendation["action"], [])
            if action in available_actions
        ]

        return {
            "execution_order": 0,
            "target": recommendation["target"],
            "line": recommendation["line"],
            "action": recommendation["action"],
            "priority": priority,
            "dependencies": dependencies,
            "impact": {
                "benefit_score": benefit,
                "effort_points": effort,
                "risk": self._risk(risk_score),
                "risk_score": risk_score,
                "complexity_reduction_percent": min(20, benefit * 2),
                "technical_debt_reduction_percent": min(25, benefit * 2 + evidence_count),
                "confidence": recommendation["confidence"],
            },
            "evidence": recommendation["evidence"],
            "rationale": (
                f"Scheduled from a {priority}-priority recommendation with benefit {benefit}, "
                f"effort {effort}, risk {self._risk(risk_score)}, and {len(dependencies)} prerequisite(s)."
            ),
        }

    def _risk(self, score: int) -> str:
        if score >= self.policy.high_risk_threshold:
            return "high"
        if score >= self.policy.medium_risk_threshold:
            return "medium"
        return "low"

    @staticmethod
    def _validate_dependencies(plan: list[dict[str, Any]]) -> None:
        actions = {item["action"] for item in plan}
        missing = sorted({dep for item in plan for dep in item["dependencies"] if dep not in actions})
        if missing:
            raise ValueError(f"Missing refactoring dependencies: {', '.join(missing)}")

    @staticmethod
    def _topological_order(plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_action = {item["action"]: item for item in plan}
        remaining = {action: set(item["dependencies"]) for action, item in by_action.items()}
        ordered: list[dict[str, Any]] = []

        while remaining:
            ready = sorted(
                (action for action, deps in remaining.items() if not deps),
                key=lambda action: (
                    {"high": 0, "medium": 1, "low": 2}[by_action[action]["priority"]],
                    -by_action[action]["impact"]["benefit_score"],
                    by_action[action]["line"],
                    action,
                ),
            )
            if not ready:
                cycle = ", ".join(sorted(remaining))
                raise ValueError(f"Circular refactoring dependency detected: {cycle}")
            for action in ready:
                ordered.append(by_action[action])
                remaining.pop(action)
                for deps in remaining.values():
                    deps.discard(action)

        return ordered
