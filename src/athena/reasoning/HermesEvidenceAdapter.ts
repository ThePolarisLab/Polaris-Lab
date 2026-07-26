import type { AnyExecutiveEntity, EvidenceReference } from "../../hermes/executive";
import type { EvidenceStrength, ReasoningEvidence } from "./contracts";

const strengthFor = (confidence: number): EvidenceStrength => {
  if (confidence >= 0.8) return "strong";
  if (confidence >= 0.5) return "moderate";
  return "weak";
};

const evidenceId = (entity: AnyExecutiveEntity, reference: EvidenceReference): string =>
  [entity.organizationId, reference.connectorId, reference.resourceType, reference.resourceId].join(":");

/**
 * Converts governed Hermes executive entities into Athena reasoning evidence.
 *
 * This is Athena's compatibility boundary. It intentionally depends only on
 * Hermes' public executive barrel and preserves the original evidence
 * reference in attributes so an insight can be traced back to its source.
 */
export const toAthenaReasoningEvidence = (
  organizationId: string,
  entities: readonly AnyExecutiveEntity[],
): ReasoningEvidence[] => {
  const foreignEntity = entities.find((entity) => entity.organizationId !== organizationId);
  if (foreignEntity) {
    throw new Error(`Executive entity ${foreignEntity.id} belongs to another organization`);
  }

  return entities
    .flatMap((entity) =>
      entity.evidence.map((reference) => ({
        id: evidenceId(entity, reference),
        organizationId,
        domain: entity.kind,
        source: reference.connectorId,
        observedAt: new Date(reference.observedAt),
        summary: `${entity.kind} ${entity.id} from ${reference.connectorId}`,
        strength: strengthFor(reference.confidence),
        reliability: reference.confidence,
        completeness: 1,
        attributes: {
          executiveEntityId: entity.id,
          executiveEntityVersion: entity.version,
          evidenceReference: { ...reference },
        },
      })),
    )
    .sort((left, right) => left.id.localeCompare(right.id));
};
