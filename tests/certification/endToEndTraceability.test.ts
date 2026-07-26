import { EvidenceEnvelope } from "../../src/hermes/connectors/contracts";
import {
  ExecutiveProjectionEngine,
  InMemoryExecutiveRepository,
  MotiveVehicleProjection,
  OutlookTaskProjection,
  QuickBooksFinancialProjection,
} from "../../src/hermes/executive";
import { ExecutiveQueryEngine, ExecutiveReadQueryRepository } from "../../src/hermes/query";

function evidence(
  provider: string,
  recordId: string,
  payload: Record<string, unknown>,
  organizationId = "org-1",
): EvidenceEnvelope<Record<string, unknown>> {
  return {
    organizationId,
    tenantId: `${organizationId}-tenant`,
    source: {
      connectorId: `${provider}-connector`,
      provider,
      sourceRecordId: recordId,
      sourceReference: `https://source.example/${provider}/${recordId}`,
    },
    observedAt: "2026-07-25T00:00:00.000Z",
    ingestedAt: "2026-07-25T00:01:00.000Z",
    correlationId: `correlation:${provider}:${recordId}`,
    schemaVersion: "1",
    idempotencyKey: `${organizationId}:${provider}:${recordId}`,
    payload,
  };
}

function buildPipeline() {
  const repository = new InMemoryExecutiveRepository();
  const projectionEngine = new ExecutiveProjectionEngine(
    repository,
    () => "2026-07-25T02:00:00.000Z",
  );
  projectionEngine.register(new MotiveVehicleProjection());
  projectionEngine.register(new OutlookTaskProjection());
  projectionEngine.register(new QuickBooksFinancialProjection());

  const queryEngine = new ExecutiveQueryEngine(
    new ExecutiveReadQueryRepository(repository),
    () => "2026-07-25T03:00:00.000Z",
  );

  return { repository, projectionEngine, queryEngine };
}

describe("PGE-009.10.3 end-to-end integration and traceability", () => {
  it("preserves source provenance from evidence through projection and query", async () => {
    const { projectionEngine, queryEngine } = buildPipeline();
    const source = evidence("motive", "vehicle-22", {
      resourceType: "vehicle",
      unitNumber: "TRK-22",
      status: "assigned",
      utilizationPercent: 84,
    });

    const execution = await projectionEngine.project(source);
    const result = await queryEngine.fleet(
      { organizationId: "org-1" },
      { limit: 10 },
    );

    expect(execution.skipped).toBe(false);
    expect(execution.projectionIds).toEqual(["motive-vehicle-projection"]);
    expect(execution.entityIds).toEqual(["vehicle:org-1:vehicle-22"]);
    expect(result.items).toHaveLength(1);
    expect(result.items[0].evidence).toEqual([
      {
        connectorId: "motive-connector",
        resourceType: "motive",
        resourceId: "vehicle-22",
        observedAt: source.observedAt,
        confidence: 1,
        sourceUrl: "https://source.example/motive/vehicle-22",
      },
    ]);
    expect(result.items[0].externalReferences).toEqual([
      {
        system: "motive",
        resourceType: "vehicle",
        resourceId: "vehicle-22",
      },
    ]);
  });

  it("coexists across connectors while retaining independent lineage", async () => {
    const { projectionEngine, queryEngine } = buildPipeline();

    await projectionEngine.project(
      evidence("outlook", "message-9", {
        resourceType: "message",
        subject: "Confirm customer payment date",
        requiresFollowUp: true,
        importance: "high",
      }),
    );
    await projectionEngine.project(
      evidence("quickbooks", "cash-1", {
        resourceType: "cash-flow",
        amount: 50000,
        currency: "CAD",
        asOf: "2026-07-24",
      }),
    );

    const dashboard = await queryEngine.dashboard({ organizationId: "org-1" });
    const tasks = await queryEngine.tasks({ organizationId: "org-1" }, { limit: 10 });
    const finance = await queryEngine.financials({ organizationId: "org-1" }, { limit: 10 });

    expect(dashboard.finance?.cashPosition?.amount).toBe(50000);
    expect(tasks.items[0].evidence[0].connectorId).toBe("outlook-connector");
    expect(tasks.items[0].evidence[0].resourceId).toBe("message-9");
    expect(finance.items[0].evidence[0].connectorId).toBe("quickbooks-connector");
    expect(finance.items[0].evidence[0].resourceId).toBe("cash-1");
  });

  it("is deterministic and idempotent for duplicate evidence", async () => {
    const { repository, projectionEngine } = buildPipeline();
    const source = evidence("motive", "vehicle-22", {
      resourceType: "vehicle",
      unitNumber: "TRK-22",
      status: "assigned",
      utilizationPercent: 84,
    });

    const first = await projectionEngine.project(source);
    const before = await repository.getById("vehicle:org-1:vehicle-22");
    const replay = await projectionEngine.project(source);
    const after = await repository.getById("vehicle:org-1:vehicle-22");

    expect(first.skipped).toBe(false);
    expect(replay).toEqual({
      evidenceKey: source.idempotencyKey,
      projectionIds: [],
      entityIds: [],
      eventIds: [],
      skipped: true,
    });
    expect(after).toEqual(before);
  });

  it("fails closed across organization boundaries at query time", async () => {
    const { projectionEngine, queryEngine } = buildPipeline();
    await projectionEngine.project(
      evidence(
        "motive",
        "vehicle-private",
        {
          resourceType: "vehicle",
          unitNumber: "PRIVATE-1",
          status: "available",
          utilizationPercent: 20,
        },
        "org-private",
      ),
    );

    const visible = await queryEngine.fleet(
      { organizationId: "org-private" },
      { limit: 10 },
    );
    const hidden = await queryEngine.fleet(
      { organizationId: "org-1" },
      { limit: 10 },
    );

    expect(visible.items.map((item) => item.id)).toEqual([
      "vehicle:org-private:vehicle-private",
    ]);
    expect(hidden.items).toEqual([]);
  });
});
