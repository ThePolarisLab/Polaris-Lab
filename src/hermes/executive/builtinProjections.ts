import { EvidenceEnvelope } from "../connectors/contracts";
import {
  ExecutiveFinancialSnapshot,
  ExecutiveTask,
  ExecutiveVehicle,
  Money,
} from "./contracts";
import { ExecutiveProjection, ProjectionContext, ProjectionResult } from "./projections";

type RecordPayload = Readonly<Record<string, unknown>>;

abstract class ProviderProjection implements ExecutiveProjection<RecordPayload> {
  abstract readonly id: string;
  readonly priority = 100;
  protected abstract readonly provider: string;
  protected abstract readonly resourceTypes: readonly string[];

  supports(evidence: EvidenceEnvelope): evidence is EvidenceEnvelope<RecordPayload> {
    const resourceType = readString(evidence.payload, "resourceType") ?? readString(evidence.extensions, "resourceType");
    return evidence.source.provider.toLowerCase() === this.provider && !!resourceType && this.resourceTypes.includes(resourceType);
  }

  abstract project(evidence: EvidenceEnvelope<RecordPayload>, context: ProjectionContext): Promise<ProjectionResult>;
}

export class QuickBooksFinancialProjection extends ProviderProjection {
  readonly id = "quickbooks-financial-snapshot";
  protected readonly provider = "quickbooks";
  protected readonly resourceTypes = ["profit-and-loss", "balance-sheet", "cash-flow", "ar-aging", "ap-aging"];

  async project(evidence: EvidenceEnvelope<RecordPayload>, context: ProjectionContext): Promise<ProjectionResult> {
    const id = `financial-snapshot:${evidence.organizationId}`;
    const existing = await context.getExisting<ExecutiveFinancialSnapshot>(id);
    const currency = readString(evidence.payload, "currency") ?? existing?.cashPosition?.currency ?? "CAD";
    const resourceType = readString(evidence.payload, "resourceType")!;
    const amount = readNumber(evidence.payload, "amount");
    const money = amount === undefined ? undefined : ({ amount, currency } as Money);
    const timestamp = context.now();

    const entity: ExecutiveFinancialSnapshot = {
      ...(existing ?? {}),
      id,
      kind: "financial-snapshot",
      organizationId: evidence.organizationId,
      version: await context.nextVersion(id),
      asOf: readString(evidence.payload, "asOf") ?? evidence.observedAt,
      cashPosition: resourceType === "cash-flow" ? money : existing?.cashPosition,
      accountsReceivable: resourceType === "ar-aging" ? money : existing?.accountsReceivable,
      accountsPayable: resourceType === "ap-aging" ? money : existing?.accountsPayable,
      revenue: resourceType === "profit-and-loss" ? money : existing?.revenue,
      expenses: existing?.expenses,
      netProfit: resourceType === "profit-and-loss" ? optionalMoney(evidence.payload, "netProfit", currency) : existing?.netProfit,
      externalReferences: mergeUnique(existing?.externalReferences, context.externalReference(evidence, resourceType)),
      evidence: mergeUnique(existing?.evidence, context.evidenceReference(evidence)),
      createdAt: existing?.createdAt ?? timestamp,
      updatedAt: timestamp,
      metadata: { ...(existing?.metadata ?? {}), lastProjection: this.id },
    };
    return { entities: [entity] };
  }
}

export class MotiveVehicleProjection extends ProviderProjection {
  readonly id = "motive-vehicle";
  protected readonly provider = "motive";
  protected readonly resourceTypes = ["vehicle", "vehicle-utilization"];

  async project(evidence: EvidenceEnvelope<RecordPayload>, context: ProjectionContext): Promise<ProjectionResult> {
    const sourceId = evidence.source.sourceRecordId;
    const id = `vehicle:${evidence.organizationId}:${sourceId}`;
    const existing = await context.getExisting<ExecutiveVehicle>(id);
    const timestamp = context.now();
    const rawStatus = readString(evidence.payload, "status");
    const status = rawStatus === "assigned" || rawStatus === "maintenance" || rawStatus === "out-of-service" ? rawStatus : existing?.status ?? "available";
    const entity: ExecutiveVehicle = {
      ...(existing ?? {}),
      id,
      kind: "vehicle",
      organizationId: evidence.organizationId,
      version: await context.nextVersion(id),
      unitNumber: readString(evidence.payload, "unitNumber") ?? existing?.unitNumber ?? sourceId,
      status,
      currentDriverId: readString(evidence.payload, "currentDriverId") ?? existing?.currentDriverId,
      currentLoadId: readString(evidence.payload, "currentLoadId") ?? existing?.currentLoadId,
      utilizationPercent: readNumber(evidence.payload, "utilizationPercent") ?? existing?.utilizationPercent,
      externalReferences: mergeUnique(existing?.externalReferences, context.externalReference(evidence, "vehicle")),
      evidence: mergeUnique(existing?.evidence, context.evidenceReference(evidence)),
      createdAt: existing?.createdAt ?? timestamp,
      updatedAt: timestamp,
      metadata: { ...(existing?.metadata ?? {}), lastProjection: this.id },
    };
    return { entities: [entity] };
  }
}

export class OutlookTaskProjection extends ProviderProjection {
  readonly id = "outlook-follow-up-task";
  protected readonly provider = "outlook";
  protected readonly resourceTypes = ["message"];

  async project(evidence: EvidenceEnvelope<RecordPayload>, context: ProjectionContext): Promise<ProjectionResult> {
    if (readBoolean(evidence.payload, "requiresFollowUp") !== true) return { entities: [] };
    const id = `task:${evidence.organizationId}:outlook:${evidence.source.sourceRecordId}`;
    const existing = await context.getExisting<ExecutiveTask>(id);
    const timestamp = context.now();
    const entity: ExecutiveTask = {
      ...(existing ?? {}),
      id,
      kind: "task",
      organizationId: evidence.organizationId,
      version: await context.nextVersion(id),
      title: readString(evidence.payload, "subject") ?? "Follow up on Outlook message",
      status: existing?.status ?? "open",
      priority: readString(evidence.payload, "importance") === "high" ? "high" : existing?.priority ?? "medium",
      dueAt: readString(evidence.payload, "dueAt") ?? existing?.dueAt,
      externalReferences: mergeUnique(existing?.externalReferences, context.externalReference(evidence, "message")),
      evidence: mergeUnique(existing?.evidence, context.evidenceReference(evidence, 0.9)),
      createdAt: existing?.createdAt ?? timestamp,
      updatedAt: timestamp,
      metadata: { ...(existing?.metadata ?? {}), lastProjection: this.id },
    };
    return { entities: [entity] };
  }
}

export function registerDefaultExecutiveProjections(engine: { register(projection: ExecutiveProjection): void }): void {
  engine.register(new QuickBooksFinancialProjection());
  engine.register(new MotiveVehicleProjection());
  engine.register(new OutlookTaskProjection());
}

function readString(value: unknown, key: string): string | undefined {
  if (!value || typeof value !== "object") return undefined;
  const candidate = (value as Record<string, unknown>)[key];
  return typeof candidate === "string" && candidate.trim() ? candidate : undefined;
}
function readNumber(value: unknown, key: string): number | undefined {
  if (!value || typeof value !== "object") return undefined;
  const candidate = (value as Record<string, unknown>)[key];
  return typeof candidate === "number" && Number.isFinite(candidate) ? candidate : undefined;
}
function readBoolean(value: unknown, key: string): boolean | undefined {
  if (!value || typeof value !== "object") return undefined;
  const candidate = (value as Record<string, unknown>)[key];
  return typeof candidate === "boolean" ? candidate : undefined;
}
function optionalMoney(value: unknown, key: string, currency: string): Money | undefined {
  const amount = readNumber(value, key);
  return amount === undefined ? undefined : { amount, currency };
}
function mergeUnique<T>(existing: readonly T[] | undefined, item: T): readonly T[] {
  const serialized = JSON.stringify(item);
  return Object.freeze([...(existing ?? []).filter((candidate) => JSON.stringify(candidate) !== serialized), item]);
}
