"""Deterministic refactoring recommendations built from measured findings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.refactoring.smells import PythonCodeSmellDetector


@dataclass(frozen=True)
class RecommendationPolicy:
    """Policy for prioritizing and grouping refactoring recommendations."""

    high_severity_weight: int = 5
    medium_severity_weight: int = 3
    low_severity_weight: int = 1
    high_priority_threshold: int = 8
    medium_priority_threshold: int = 3

    def __post_init__(self) -> None:
        values = self.__dict__.values()
        if any(not isinstance(value, int) or value < 0 for value in values):
            raise ValueError("Recommendation policy values must be non-negative integers.")
        if self.high_priority_threshold < self.medium_priority_threshold:
            raise ValueError("High priority threshold must be at least the medium threshold.")


class PythonRefactoringAdvisor:
    """Convert deterministic smell findings into an explainable action plan."""

    _SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

    def __init__(self, policy: RecommendationPolicy | None = None) -> None:
        self.policy = policy or RecommendationPolicy()

    def analyze(self, source: str, path: str = "<memory>") -> dict[str, Any]:
        smell_analysis = PythonCodeSmellDetector().analyze(source, path)
        grouped: dict[tuple[str | None, str], list[dict[str, Any]]] = {}

        for finding in smell_analysis["findings"]:
            key = (finding.get("qualified_name"), finding["recommendation"])
            grouped.setdefault(key, []).append(finding)

        recommendations = [
            self._build_recommendation(target, action, findings)
            for (target, action), findings in grouped.items()
        ]
        recommendations.sort(
            key=lambda item: (
                {"high": 0, "medium": 1, "low": 2}[item["priority"]],
                item["line"],
                item["action"],
            )
        )
        for index, item in enumerate(recommendations, start=1):
            item["rank"] = index

        return {
            "path": path,
            "metrics": {
                "total_recommendations": len(recommendations),
                "high_priority": sum(item["priority"] == "high" for item in recommendations),
                "medium_priority": sum(item["priority"] == "medium" for item in recommendations),
                "low_priority": sum(item["priority"] == "low" for item in recommendations),
            },
            "policy": self.policy.__dict__,
            "recommendations": recommendations,
            "source_findings": smell_analysis["metrics"],
            "guardrails": {
                "deterministic": True,
                "executes_source": False,
                "modifies_source": False,
                "automatic_rewrite": False,
            },
        }

    def _build_recommendation(
        self,
        target: str | None,
        action: str,
        findings: list[dict[str, Any]],
    ) -> dict[str, Any]:
        score = sum(self._severity_weight(item["severity"]) for item in findings)
        priority = self._priority(score)
        severities = sorted(
            {item["severity"] for item in findings},
            key=self._SEVERITY_ORDER.__getitem__,
        )
        smell_types = sorted({item["type"] for item in findings})
        confidence = round(sum(item["confidence"] for item in findings) / len(findings), 4)
        first_line = min(item["line"] for item in findings)
        last_line = max(item["end_line"] for item in findings)

        return {
            "rank": 0,
            "priority": priority,
            "score": score,
            "target": target or "module",
            "line": first_line,
            "end_line": last_line,
            "action": action,
            "smell_types": smell_types,
            "severities": severities,
            "confidence": confidence,
            "evidence": [
                {
                    "type": item["type"],
                    "severity": item["severity"],
                    "line": item["line"],
                    "end_line": item["end_line"],
                    "details": item["evidence"],
                }
                for item in findings
            ],
            "rationale": (
                f"Prioritized as {priority} from {len(findings)} deterministic finding(s) "
                f"with score {score} and average confidence {confidence}."
            ),
        }

    def _severity_weight(self, severity: str) -> int:
        return {
            "high": self.policy.high_severity_weight,
            "medium": self.policy.medium_severity_weight,
            "low": self.policy.low_severity_weight,
        }[severity]

    def _priority(self, score: int) -> str:
        if score >= self.policy.high_priority_threshold:
            return "high"
        if score >= self.policy.medium_priority_threshold:
            return "medium"
        return "low"
