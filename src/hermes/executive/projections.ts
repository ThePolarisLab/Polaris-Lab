import { EvidenceEnvelope } from "../connectors/contracts";
import { AnyExecutiveEntity, BusinessEvent, EvidenceReference, ExternalReference } from "./contracts";
import { ExecutiveRepository } from "./repository";

export interface ProjectionResult {
  readonly entities: readonly AnyExecutiveEntity[];
  readonly events?: readonly BusinessEvent[];
}

export interface ExecutiveProjection<TPayload = unknown> {
  readonly id: string;
  readonly priority?: number;
  supports(evidence: EvidenceEnvelope): evidence is EvidenceEnvelope<TPayload>;
  project(evidence: EvidenceEnvelope<TPayload>, context: ProjectionContext): Promise<ProjectionResult>;
}

export interface ProjectionContext {
  readonly repository: ExecutiveRepository;
  readonly now: () => string;
  getExisting<T extends AnyExecutiveEntity = AnyExecutiveEntity>(id: string): Promise<T | undefined>;
  nextVersion(id: string): Promise<number>;
  evidenceReference(evidence: EvidenceEnvelope, confidence?: number): EvidenceReference;
  externalReference(evidence: EvidenceEnvelope, resourceType: string): ExternalReference;
}

export interface ProjectionExecutionResult {
  readonly evidenceKey: string;
  readonly projectionIds: readonly string[];
  readonly entityIds: readonly string[];
  readonly eventIds: readonly string[];
  readonly skipped: boolean;
}

export class ExecutiveProjectionEngine {
  private readonly projections = new Map<string, ExecutiveProjection>();
  private readonly processedEvidence = new Set<string>();

  constructor(
    private readonly repository: ExecutiveRepository,
    private readonly now: () => string = () => new Date().toISOString(),
  ) {}

  register(projection: ExecutiveProjection): void {
    if (!projection.id.trim()) throw new Error("Projection id is required");
    if (this.projections.has(projection.id)) throw new Error(`Projection already registered: ${projection.id}`);
    this.projections.set(projection.id, projection);
  }

  listProjectionIds(): readonly string[] {
    return Object.freeze([...this.projections.keys()].sort());
  }

  async project(evidence: EvidenceEnvelope): Promise<ProjectionExecutionResult> {
    if (!evidence.organizationId.trim() || !evidence.idempotencyKey.trim()) {
      throw new Error("Evidence organization id and idempotency key are required");
    }
    if (this.processedEvidence.has(evidence.idempotencyKey)) {
      return freezeExecution(evidence.idempotencyKey, [], [], [], true);
    }

    const matching = [...this.projections.values()]
      .filter((projection) => projection.supports(evidence))
      .sort((left, right) => (left.priority ?? 100) - (right.priority ?? 100) || left.id.localeCompare(right.id));

    const context: ProjectionContext = {
      repository: this.repository,
      now: this.now,
      getExisting: (id) => this.repository.getById(id),
      nextVersion: async (id) => ((await this.repository.getById(id))?.version ?? 0) + 1,
      evidenceReference: (item, confidence = 1) => ({
        connectorId: item.source.connectorId,
        resourceType: item.source.provider,
        resourceId: item.source.sourceRecordId,
        observedAt: item.observedAt,
        confidence,
        sourceUrl: item.source.sourceReference,
      }),
      externalReference: (item, resourceType) => ({
        system: item.source.provider,
        resourceType,
        resourceId: item.source.sourceRecordId,
      }),
    };

    const entityIds: string[] = [];
    const eventIds: string[] = [];
    for (const projection of matching) {
      const result = await projection.project(evidence, context);
      for (const entity of result.entities) {
        if (entity.organizationId !== evidence.organizationId) {
          throw new Error(`Projection ${projection.id} produced a cross-organization entity`);
        }
        await this.repository.upsert(entity);
        entityIds.push(entity.id);
      }
      for (const event of result.events ?? []) {
        if (event.organizationId !== evidence.organizationId) {
          throw new Error(`Projection ${projection.id} produced a cross-organization event`);
        }
        await this.repository.appendEvent(event);
        eventIds.push(event.id);
      }
    }

    this.processedEvidence.add(evidence.idempotencyKey);
    return freezeExecution(evidence.idempotencyKey, matching.map((item) => item.id), entityIds, eventIds, false);
  }
}

function freezeExecution(
  evidenceKey: string,
  projectionIds: string[],
  entityIds: string[],
  eventIds: string[],
  skipped: boolean,
): ProjectionExecutionResult {
  return Object.freeze({
    evidenceKey,
    projectionIds: Object.freeze([...projectionIds]),
    entityIds: Object.freeze([...entityIds]),
    eventIds: Object.freeze([...eventIds]),
    skipped,
  });
}
