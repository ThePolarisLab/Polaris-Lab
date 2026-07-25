import {
  ExecutiveProjectionEngine,
  InMemoryExecutiveRepository,
  MotiveVehicleProjection,
  OutlookTaskProjection,
  QuickBooksFinancialProjection,
} from "../../src/hermes/executive";
import { EvidenceEnvelope } from "../../src/hermes/connectors/contracts";

function evidence(provider: string, recordId: string, payload: Record<string, unknown>, key = `${provider}:${recordId}`): EvidenceEnvelope<Record<string, unknown>> {
  return {
    organizationId: "org-1",
    tenantId: "tenant-1",
    source: { connectorId: `${provider}-connector`, provider, sourceRecordId: recordId },
    observedAt: "2026-07-25T00:00:00.000Z",
    ingestedAt: "2026-07-25T00:01:00.000Z",
    correlationId: "correlation-1",
    schemaVersion: "1",
    idempotencyKey: key,
    payload,
  };
}

describe("ExecutiveProjectionEngine", () => {
  it("projects QuickBooks evidence incrementally and skips duplicate evidence", async () => {
    const repository = new InMemoryExecutiveRepository();
    const engine = new ExecutiveProjectionEngine(repository, () => "2026-07-25T02:00:00.000Z");
    engine.register(new QuickBooksFinancialProjection());

    const first = await engine.project(evidence("quickbooks", "pnl-1", {
      resourceType: "profit-and-loss",
      amount: 125000,
      netProfit: 22000,
      currency: "CAD",
      asOf: "2026-07-24",
    }));
    const duplicate = await engine.project(evidence("quickbooks", "pnl-1", {
      resourceType: "profit-and-loss",
      amount: 125000,
    }));

    expect(first.entityIds).toEqual(["financial-snapshot:org-1"]);
    expect(duplicate.skipped).toBe(true);
    const snapshot: any = await repository.getById("financial-snapshot:org-1");
    expect(snapshot.revenue).toEqual({ amount: 125000, currency: "CAD" });
    expect(snapshot.netProfit.amount).toBe(22000);
    expect(snapshot.version).toBe(1);
  });

  it("combines separate financial reports into one versioned snapshot", async () => {
    const repository = new InMemoryExecutiveRepository();
    const engine = new ExecutiveProjectionEngine(repository, () => "2026-07-25T02:00:00.000Z");
    engine.register(new QuickBooksFinancialProjection());

    await engine.project(evidence("quickbooks", "cash-1", { resourceType: "cash-flow", amount: 50000, currency: "CAD" }));
    await engine.project(evidence("quickbooks", "ar-1", { resourceType: "ar-aging", amount: 18000, currency: "CAD" }));

    const snapshot: any = await repository.getById("financial-snapshot:org-1");
    expect(snapshot.cashPosition.amount).toBe(50000);
    expect(snapshot.accountsReceivable.amount).toBe(18000);
    expect(snapshot.version).toBe(2);
    expect(snapshot.evidence).toHaveLength(2);
  });

  it("projects Motive vehicles and Outlook follow-up tasks", async () => {
    const repository = new InMemoryExecutiveRepository();
    const engine = new ExecutiveProjectionEngine(repository, () => "2026-07-25T02:00:00.000Z");
    engine.register(new MotiveVehicleProjection());
    engine.register(new OutlookTaskProjection());

    await engine.project(evidence("motive", "vehicle-22", {
      resourceType: "vehicle",
      unitNumber: "TRK-22",
      status: "assigned",
      utilizationPercent: 84,
    }));
    await engine.project(evidence("outlook", "message-9", {
      resourceType: "message",
      subject: "Confirm customer payment date",
      requiresFollowUp: true,
      importance: "high",
    }));

    const vehicle: any = await repository.getById("vehicle:org-1:vehicle-22");
    const task: any = await repository.getById("task:org-1:outlook:message-9");
    expect(vehicle.unitNumber).toBe("TRK-22");
    expect(vehicle.utilizationPercent).toBe(84);
    expect(task.priority).toBe("high");
    expect(task.title).toBe("Confirm customer payment date");
  });

  it("rejects duplicate projection registration", () => {
    const engine = new ExecutiveProjectionEngine(new InMemoryExecutiveRepository());
    engine.register(new MotiveVehicleProjection());
    expect(() => engine.register(new MotiveVehicleProjection())).toThrow("Projection already registered");
  });
});
