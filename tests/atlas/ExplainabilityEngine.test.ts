import { ExplainabilityEngine, GraphPath } from "../../src/atlas";

const now = new Date("2026-07-19T12:00:00Z");

const project = {
  id: "project",
  type: "project" as const,
  name: "Atlas",
  metadata: {},
  tags: [],
  status: "active" as const,
  version: 1,
  createdAt: now,
  updatedAt: now,
};

const repository = {
  ...project,
  id: "repo",
  type: "repository" as const,
  name: "Polaris-Lab",
};

const release = {
  ...project,
  id: "release",
  type: "release" as const,
  name: "v0.6.0",
};

const path: GraphPath = {
  start: project,
  end: release,
  depth: 2,
  steps: [
    {
      from: project,
      to: repository,
      direction: "outgoing",
      relationship: {
        id: "rel-1",
        sourceEntityId: "project",
        targetEntityId: "repo",
        type: "owns",
        metadata: {},
        confidence: 0.9,
        status: "active",
        version: 1,
        createdAt: now,
        updatedAt: now,
      },
    },
    {
      from: repository,
      to: release,
      direction: "outgoing",
      relationship: {
        id: "rel-2",
        sourceEntityId: "repo",
        targetEntityId: "release",
        type: "produces",
        metadata: {},
        confidence: 0.8,
        status: "active",
        version: 1,
        createdAt: now,
        updatedAt: now,
      },
    },
  ],
};

describe("Atlas Explainability Engine", () => {
  test("turns a graph path into a readable evidence narrative", () => {
    const explanation = new ExplainabilityEngine().explainPath(path);

    expect(explanation.summary).toContain("2 relationships");
    expect(explanation.narrative).toContain("Atlas (project) owns Polaris-Lab (repository)");
    expect(explanation.narrative).toContain("Polaris-Lab (repository) produces v0.6.0 (release)");
    expect(explanation.steps).toHaveLength(2);
    expect(explanation.evidence).toHaveLength(3);
  });

  test("uses the weakest relationship as the path confidence", () => {
    const explanation = new ExplainabilityEngine().explainPath(path);
    expect(explanation.confidence).toBe(0.8);
  });

  test("can omit type labels and evidence relationship identifiers", () => {
    const explanation = new ExplainabilityEngine().explainPath(path, {
      includeEntityTypes: false,
      includeEvidenceIds: false,
    });

    expect(explanation.narrative).toBe("Atlas owns Polaris-Lab. Polaris-Lab produces v0.6.0.");
    expect(explanation.evidence[1].relationshipId).toBeUndefined();
  });

  test("rejects inconsistent path depth", () => {
    expect(() => new ExplainabilityEngine().explainPath({ ...path, depth: 3 }))
      .toThrow("depth does not match");
  });

  test("explains a zero-hop path", () => {
    const explanation = new ExplainabilityEngine().explainPath({
      start: project,
      end: project,
      depth: 0,
      steps: [],
    });

    expect(explanation.summary).toBe("Atlas is the requested entity.");
    expect(explanation.confidence).toBe(1);
    expect(explanation.narrative).toBe("");
  });
});
