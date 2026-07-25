import { InMemoryExecutiveRepository } from "../../src/hermes/executive";
import { ExecutiveQueryEngine, ExecutiveReadQueryRepository } from "../../src/hermes/query";

const base = {
  organizationId: "org-1",
  version: 1,
  externalReferences: [],
  evidence: [],
  createdAt: "2026-07-25T00:00:00.000Z",
  updatedAt: "2026-07-25T00:00:00.000Z",
  metadata: {},
};

describe("ExecutiveQueryEngine", () => {
  it("filters, sorts, paginates, and isolates organizations", async () => {
    const store = new InMemoryExecutiveRepository();
    await store.upsert({ ...base, id: "v-1", kind: "vehicle", unitNumber: "101", status: "available", utilizationPercent: 35 });
    await store.upsert({ ...base, id: "v-2", kind: "vehicle", unitNumber: "102", status: "assigned", utilizationPercent: 70 });
    await store.upsert({ ...base, organizationId: "org-2", id: "v-3", kind: "vehicle", unitNumber: "201", status: "available", utilizationPercent: 10 });

    const engine = new ExecutiveQueryEngine(new ExecutiveReadQueryRepository(store));
    const result = await engine.fleet({ organizationId: "org-1" }, { utilizationBelow: 60, limit: 10 });

    expect(result.total).toBe(1);
    expect(result.items.map((item) => item.id)).toEqual(["v-1"]);
    expect(result.hasMore).toBe(false);
  });

  it("returns business-ready dashboard summaries", async () => {
    const store = new InMemoryExecutiveRepository();
    await store.upsert({ ...base, id: "c-1", kind: "customer", name: "North", status: "active" });
    await store.upsert({ ...base, id: "c-2", kind: "customer", name: "Risk", status: "at-risk", riskScore: 91 });
    await store.upsert({ ...base, id: "v-1", kind: "vehicle", unitNumber: "101", status: "available", utilizationPercent: 40 });
    await store.upsert({ ...base, id: "v-2", kind: "vehicle", unitNumber: "102", status: "maintenance", utilizationPercent: 80 });
    await store.upsert({ ...base, id: "d-1", kind: "driver", name: "A", status: "available" });
    await store.upsert({ ...base, id: "l-1", kind: "load", status: "in-transit" });
    await store.upsert({ ...base, id: "a-1", kind: "alert", severity: "critical", category: "ops", title: "Delay", description: "Late" });
    await store.upsert({ ...base, id: "t-1", kind: "task", title: "Call", status: "open", priority: "critical" });
    await store.upsert({ ...base, id: "f-1", kind: "financial-snapshot", asOf: "2026-07-24", cashPosition: { amount: 50000, currency: "CAD" } });

    const engine = new ExecutiveQueryEngine(new ExecutiveReadQueryRepository(store), () => "2026-07-25T12:00:00.000Z");
    const dashboard = await engine.dashboard({ organizationId: "org-1" });

    expect(dashboard.generatedAt).toBe("2026-07-25T12:00:00.000Z");
    expect(dashboard.customers).toEqual({ active: 1, atRisk: 1 });
    expect(dashboard.fleet).toEqual({ available: 1, maintenance: 1, averageUtilizationPercent: 60 });
    expect(dashboard.operations).toEqual({ activeLoads: 1, availableDrivers: 1 });
    expect(dashboard.finance?.cashPosition?.amount).toBe(50000);
    expect(dashboard.risk).toEqual({ criticalAlerts: 1, openCriticalTasks: 1 });
  });

  it("supports nested money filters and blocks cross-organization reads", async () => {
    const store = new InMemoryExecutiveRepository();
    await store.upsert({ ...base, id: "c-1", kind: "customer", name: "A", status: "active", lifetimeRevenue: { amount: 100000, currency: "CAD" } });
    const queryRepository = new ExecutiveReadQueryRepository(store);

    const result = await queryRepository.search({ organizationId: "org-1" }, { kind: "customer", filters: [{ field: "lifetimeRevenue.amount", operator: "gte", value: 90000 }] });
    const hidden = await queryRepository.getById({ organizationId: "org-2" }, "c-1");

    expect(result.total).toBe(1);
    expect(hidden).toBeUndefined();
  });
});
