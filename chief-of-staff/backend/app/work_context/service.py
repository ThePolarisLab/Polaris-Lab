from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.work_context.connectors import MemoryConnector, MissionsConnector, TeamNotesConnector
from app.work_context.schemas import (
    ConnectorResult,
    EntityReference,
    MissingInformation,
    Recommendation,
    WorkContextResponse,
)


class WorkContextService:
    def __init__(self, connectors=None):
        self.connectors = connectors or [
            TeamNotesConnector(),
            MemoryConnector(),
            MissionsConnector(),
        ]

    def build(
        self,
        db: Session,
        *,
        work_item_id: str,
        entity_type: str,
        entity_id: str,
        display_name: str,
    ) -> WorkContextResponse:
        entity = EntityReference(
            entity_type=entity_type,
            entity_id=entity_id,
            display_name=display_name,
            confidence=1.0,
            resolution_method="explicit_request",
        )
        evidence = []
        connector_results: list[ConnectorResult] = []
        warnings: list[str] = []

        for connector in self.connectors:
            if not connector.supports(entity.entity_type):
                connector_results.append(
                    ConnectorResult(connector=connector.name, status="skipped")
                )
                continue
            try:
                connector_evidence, result = connector.fetch_context(db, entity)
                evidence.extend(connector_evidence)
                connector_results.append(result)
            except Exception as exc:  # Connector isolation is intentional.
                warning = f"{connector.name} connector failed: {exc}"
                warnings.append(warning)
                connector_results.append(
                    ConnectorResult(
                        connector=connector.name,
                        status="failed",
                        warning=warning,
                    )
                )

        missing_information = self._missing_information(evidence)
        completeness_score = self._completeness_score(
            evidence_count=len(evidence),
            successful_connectors=sum(
                result.status == "success" for result in connector_results
            ),
            total_connectors=len(self.connectors),
            missing_count=len(missing_information),
        )
        recommendation = self._recommend(entity, evidence, completeness_score)

        return WorkContextResponse(
            work_item_id=work_item_id,
            generated_at=datetime.now(timezone.utc),
            entity_refs=[entity],
            evidence=evidence,
            missing_information=missing_information,
            completeness_score=completeness_score,
            recommendation=recommendation,
            connector_results=connector_results,
            warnings=warnings,
        )

    @staticmethod
    def _missing_information(evidence):
        if evidence:
            return []
        return [
            MissingInformation(
                field="supporting_evidence",
                reason="No matching internal context was found.",
                required_for="evidence-backed recommendation",
                suggested_source="Team Notes, Memory, Missions, or an external connector",
                severity="high",
            )
        ]

    @staticmethod
    def _completeness_score(
        *, evidence_count: int, successful_connectors: int, total_connectors: int, missing_count: int
    ) -> int:
        connector_coverage = successful_connectors / max(total_connectors, 1)
        evidence_coverage = min(evidence_count / 5, 1)
        score = (connector_coverage * 50) + (evidence_coverage * 50) - (missing_count * 20)
        return max(0, min(100, round(score)))

    @staticmethod
    def _recommend(entity, evidence, completeness_score):
        if not evidence:
            return None
        evidence_ids = [item.evidence_id for item in evidence[:5]]
        priority = "high" if any(
            item.category in {"blocker", "action"} or str(item.value).lower().find("high") >= 0
            for item in evidence
        ) else "medium"
        return Recommendation(
            title=f"Review {entity.display_name} context",
            objective="Resolve the highest-value open responsibility using current internal evidence.",
            priority=priority,
            confidence=round(min(0.95, 0.5 + completeness_score / 200), 2),
            reasoning_summary=f"Athena found {len(evidence)} relevant evidence item(s) across internal Polaris sources.",
            supporting_evidence_ids=evidence_ids,
            risks=["Context may be incomplete until external connectors are added in EXP-014C."],
            alternatives=["Gather missing evidence before acting."],
            estimated_effort_minutes=15,
            suggested_owner="Founder",
        )
