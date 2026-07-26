import fs from "node:fs";
import path from "node:path";
import type { ExecutiveVehicle } from "../../src/hermes/executive";
import {
  AthenaReasoningEngine,
  ReasoningRule,
  RecommendationPolicy,
  toAthenaReasoningEvidence,
} from "../../src/athena/reasoning";

const entity = (organizationId = "org-a"): ExecutiveVehicle => ({
  id: "vehicle-214",
  kind: "vehicle",
  organizationId,
  version: 3,
  unitNumber: "214",
  status: "maintenance",
  utilizationPercent: 91,
  externalReferences: [],
  evidence: [
    {
      connectorId: "motive",
      resourceType: "vehicle",
      resourceId: "provider-214",
      observedAt: "2026-07-26T04:00:00.000Z",
      confidence: 0.94,
      sourceUrl: "https://example.invalid/vehicles/214",
    },
  ],
  createdAt: "2026-07-25T04:00:00.000Z",
  updatedAt: "2026-07-26T04:00:00.000Z",
  metadata: {},
});

const maintenanceRule: ReasoningRule = {
  id: "maintenance-rule",
  evaluate: (context) => [
    {
      id: "finding-maintenance-214",
      title: "Vehicle requires maintenance",
      description: "Vehicle 214 is currently in maintenance status.",
      domain: "fleet",
      evidenceIds: context.evidence.map((item) => item.id),
      impact: 0.8,
      urgency: 0.9,
    },
  ],
};

const maintenancePolicy: RecommendationPolicy = {
  recommend: (finding, evidence) => ({
    id: "recommendation-maintenance-214",
    findingId: finding.id,
    action: "Keep vehicle 214 out of dispatch until cleared.",
    rationale: `Supported by ${evidence.length} governed evidence item(s).`,
    expectedImpact: "Reduce service and safety risk.",
  }),
};

describe("PGE-009.10.5 Athena compatibility certification", () => {
  it("uses only the public Hermes executive contract boundary", () => {
    const athenaRoot = path.resolve(__dirname, "../../src/athena");
    const files = fs
      .readdirSync(path.join(athenaRoot, "reasoning"))
      .filter((name) => name.endsWith(".ts"));

    for (const file of files) {
      const source = fs.readFileSync(path.join(athenaRoot, "reasoning", file), "utf8");
      const hermesImports = source.match(/from\s+["'][^"']*hermes[^"']*["']/g) ?? [];
      expect(hermesImports.every((statement) => statement.includes("hermes/executive"))).toBe(true);
    }
  });

  it("preserves governed Hermes evidence references for Athena", () => {
    const [evidence] = toAthenaReasoningEvidence("org-a", [entity()]);

    expect(evidence.id).toBe("org-a:motive:vehicle:provider-214");
    expect(evidence.organizationId).toBe("org-a");
    expect(evidence.source).toBe("motive");
    expect(evidence.strength).toBe("strong");
    expect(evidence.attributes?.evidenceReference).toEqual(entity().evidence[0]);
  });

  it("fails closed when Hermes entities cross organization boundaries", () => {
    expect(() => toAthenaReasoningEvidence("org-a", [entity("org-b")])).toThrow(
      "belongs to another organization",
    );
  });

  it("produces deterministic, evidence-backed, explainable recommendations", () => {
    const evidence = toAthenaReasoningEvidence("org-a", [entity()]);
    const engine = new AthenaReasoningEngine([maintenanceRule], [maintenancePolicy]);
    const context = {
      requestId: "request-1",
      organizationId: "org-a",
      objective: "Review fleet exceptions",
      generatedAt: new Date("2026-07-26T05:00:00.000Z"),
      evidence,
    };

    const first = engine.reason(context);
    const replay = engine.reason(context);

    expect(replay).toEqual(first);
    expect(first.insights).toHaveLength(1);
    expect(first.insights[0].evidence.map((item) => item.id)).toEqual([
      "org-a:motive:vehicle:provider-214",
    ]);
    expect(first.insights[0].recommendation?.findingId).toBe("finding-maintenance-214");
    expect(first.insights[0].explanation).toContain("motive");
    expect(first.insights[0].confidence.conflicts).toEqual([]);
  });
});
