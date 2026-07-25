import {
  ExecutiveAlert,
  ExecutiveBriefingService,
  ExecutiveQueryService,
  ExecutiveVehicle,
  InMemoryExecutiveRepository,
} from "../../src/hermes/executive";

const base = {
  organizationId: "org-1",
  version: 1,
  externalReferences: [],
  evidence: [],
  createdAt: "2026-07-24T00:00:00.000Z",
  updatedAt: "2026-07-24T00:00:00.000Z",
  metadata: {},
} as const;

describe("Executive Read Model", () => {
  it("stores immutable executive entities and queries them by kind", async () => {
    const repository = new InMemoryExecutiveRepository();
    const vehicle: ExecutiveVehicle = {
      ...base,
      id: "vehicle-1",
      kind: "vehicle",
      unitNumber: "208",
      status: "available",
    };

    await repository.upsert(vehicle);

    const vehicles = await repository.listByKind<ExecutiveVehicle>("vehicle");
    expect(vehicles).toHaveLength(1);
    expect(vehicles[0].unitNumber).toBe("208");
    expect(Object.isFrozen(vehicles[0])).toBe(true);
  });

  it("rejects stale versions and cross-organization updates", async () => {
    const repository = new InMemoryExecutiveRepository();
    const vehicle: ExecutiveVehicle = {
      ...base,
      id: "vehicle-1",
      kind: "vehicle",
      unitNumber: "208",
      status: "available",
    };

    await repository.upsert(vehicle);
    await expect(repository.upsert(vehicle)).rejects.toThrow("version must increase");
    await expect(repository.upsert({ ...vehicle, organizationId: "org-2", version: 2 })).rejects.toThrow(
      "Cross-organization",
    );
  });

  it("generates an evidence-ready executive briefing", async () => {
    const repository = new InMemoryExecutiveRepository();
    const alert: ExecutiveAlert = {
      ...base,
      id: "alert-1",
      kind: "alert",
      severity: "critical",
      category: "finance",
      title: "Receivable overdue",
      description: "A material invoice is overdue.",
      recommendedAction: "Contact the customer.",
    };
    const vehicle: ExecutiveVehicle = {
      ...base,
      id: "vehicle-1",
      kind: "vehicle",
      unitNumber: "208",
      status: "available",
    };

    await repository.upsert(alert);
    await repository.upsert(vehicle);

    const query = new ExecutiveQueryService(repository);
    const briefing = await new ExecutiveBriefingService(
      query,
      () => new Date("2026-07-24T12:00:00.000Z"),
    ).generate();

    expect(briefing.headline).toContain("1 critical executive alert");
    expect(briefing.availableVehicles).toBe(1);
    expect(briefing.criticalAlerts[0].recommendedAction).toBe("Contact the customer.");
    expect(briefing.generatedAt).toBe("2026-07-24T12:00:00.000Z");
  });

  it("deduplicates business events", async () => {
    const repository = new InMemoryExecutiveRepository();
    const event = {
      id: "event-1",
      organizationId: "org-1",
      type: "InvoiceOverdue",
      occurredAt: "2026-07-24T00:00:00.000Z",
      evidence: [],
      payload: {},
    } as const;

    await repository.appendEvent(event);
    await repository.appendEvent(event);

    expect(await repository.listEvents("org-1")).toHaveLength(1);
  });
});
