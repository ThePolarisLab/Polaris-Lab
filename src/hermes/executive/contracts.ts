export type ExecutiveEntityKind =
  | "customer"
  | "load"
  | "vehicle"
  | "driver"
  | "financial-snapshot"
  | "task"
  | "alert"
  | "kpi";

export interface ExternalReference {
  readonly system: string;
  readonly resourceType: string;
  readonly resourceId: string;
}

export interface EvidenceReference {
  readonly connectorId: string;
  readonly resourceType: string;
  readonly resourceId: string;
  readonly observedAt: string;
  readonly confidence: number;
  readonly sourceUrl?: string;
}

export interface ExecutiveEntity {
  readonly id: string;
  readonly kind: ExecutiveEntityKind;
  readonly organizationId: string;
  readonly version: number;
  readonly externalReferences: readonly ExternalReference[];
  readonly evidence: readonly EvidenceReference[];
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly metadata: Readonly<Record<string, unknown>>;
}

export interface Money {
  readonly amount: number;
  readonly currency: string;
}

export interface ExecutiveCustomer extends ExecutiveEntity {
  readonly kind: "customer";
  readonly name: string;
  readonly status: "active" | "inactive" | "at-risk";
  readonly lifetimeRevenue?: Money;
  readonly outstandingReceivables?: Money;
  readonly riskScore?: number;
}

export interface ExecutiveLoad extends ExecutiveEntity {
  readonly kind: "load";
  readonly customerId?: string;
  readonly driverId?: string;
  readonly vehicleId?: string;
  readonly status: "planned" | "dispatched" | "in-transit" | "delivered" | "cancelled";
  readonly origin?: string;
  readonly destination?: string;
  readonly revenue?: Money;
  readonly estimatedCost?: Money;
}

export interface ExecutiveVehicle extends ExecutiveEntity {
  readonly kind: "vehicle";
  readonly unitNumber: string;
  readonly status: "available" | "assigned" | "maintenance" | "out-of-service";
  readonly currentDriverId?: string;
  readonly currentLoadId?: string;
  readonly utilizationPercent?: number;
}

export interface ExecutiveDriver extends ExecutiveEntity {
  readonly kind: "driver";
  readonly name: string;
  readonly status: "available" | "assigned" | "off-duty" | "unavailable";
  readonly assignedLoadId?: string;
  readonly hoursOfServiceRemaining?: number;
}

export interface ExecutiveFinancialSnapshot extends ExecutiveEntity {
  readonly kind: "financial-snapshot";
  readonly asOf: string;
  readonly cashPosition?: Money;
  readonly accountsReceivable?: Money;
  readonly accountsPayable?: Money;
  readonly revenue?: Money;
  readonly expenses?: Money;
  readonly netProfit?: Money;
}

export interface ExecutiveTask extends ExecutiveEntity {
  readonly kind: "task";
  readonly title: string;
  readonly status: "open" | "in-progress" | "completed" | "cancelled";
  readonly priority: "low" | "medium" | "high" | "critical";
  readonly dueAt?: string;
}

export interface ExecutiveAlert extends ExecutiveEntity {
  readonly kind: "alert";
  readonly severity: "info" | "warning" | "critical";
  readonly category: string;
  readonly title: string;
  readonly description: string;
  readonly recommendedAction?: string;
  readonly acknowledgedAt?: string;
}

export interface ExecutiveKpi extends ExecutiveEntity {
  readonly kind: "kpi";
  readonly name: string;
  readonly value: number;
  readonly unit: string;
  readonly measuredAt: string;
  readonly trend?: "up" | "down" | "flat";
}

export type AnyExecutiveEntity =
  | ExecutiveCustomer
  | ExecutiveLoad
  | ExecutiveVehicle
  | ExecutiveDriver
  | ExecutiveFinancialSnapshot
  | ExecutiveTask
  | ExecutiveAlert
  | ExecutiveKpi;

export interface BusinessEvent {
  readonly id: string;
  readonly organizationId: string;
  readonly type: string;
  readonly occurredAt: string;
  readonly entityId?: string;
  readonly evidence: readonly EvidenceReference[];
  readonly payload: Readonly<Record<string, unknown>>;
}

export function assertValidExecutiveEntity(entity: AnyExecutiveEntity): void {
  if (!entity.id.trim()) throw new Error("Executive entity id is required");
  if (!entity.organizationId.trim()) throw new Error("Organization id is required");
  if (!Number.isInteger(entity.version) || entity.version < 1) {
    throw new Error("Executive entity version must be a positive integer");
  }
  for (const evidence of entity.evidence) {
    if (evidence.confidence < 0 || evidence.confidence > 1) {
      throw new Error("Evidence confidence must be between 0 and 1");
    }
  }
}
