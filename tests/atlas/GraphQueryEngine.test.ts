import {
  GraphQueryEngine,
  InMemoryEntityRepository,
  InMemoryRelationshipRepository,
  KnowledgeGraph,
} from "../../src/atlas";

describe("Atlas Graph Query Engine", () => {
  const createEngine = async () => {
    const graph = new KnowledgeGraph(
      new InMemoryEntityRepository(),
      new InMemoryRelationshipRepository(),
    );

    await graph.addEntity({ id: "project", type: "project", name: "Atlas" });
    await graph.addEntity({ id: "repo", type: "repository", name: "Polaris-Lab" });
    await graph.addEntity({ id: "adr", type: "adr", name: "ADR-007" });
    await graph.addEntity({ id: "release", type: "release", name: "v0.6.0" });

    await graph.addRelationship({
      id: "owns",
      sourceEntityId: "project",
      targetEntityId: "repo",
      type: "owns",
    });
    await graph.addRelationship({
      id: "contains",
      sourceEntityId: "repo",
      targetEntityId: "adr",
      type: "contains",
    });
    await graph.addRelationship({
      id: "documents",
      sourceEntityId: "adr",
      targetEntityId: "release",
      type: "documents",
    });

    return { graph, engine: new GraphQueryEngine(graph) };
  };

  test("finds the shortest multi-hop path with an explainable trace", async () => {
    const { engine } = await createEngine();
    const path = await engine.shortestPath("project", "release", {
      direction: "outgoing",
      maxDepth: 5,
    });

    expect(path?.depth).toBe(3);
    expect(path?.steps.map((step) => step.relationship.type)).toEqual([
      "owns",
      "contains",
      "documents",
    ]);
    expect(path?.steps[2].to.id).toBe("release");
  });

  test("respects depth limits", async () => {
    const { engine } = await createEngine();
    await expect(engine.shortestPath("project", "release", {
      direction: "outgoing",
      maxDepth: 2,
    })).resolves.toBeUndefined();
  });

  test("traverses breadth-first without revisiting cycles", async () => {
    const { graph, engine } = await createEngine();
    await graph.addRelationship({
      sourceEntityId: "release",
      targetEntityId: "project",
      type: "references",
    });

    const result = await engine.traverse("project", {
      direction: "outgoing",
      maxDepth: 10,
    });

    expect(result.nodes.map((node) => node.entity.id)).toEqual(["repo", "adr", "release"]);
    expect(result.visitedEntityIds).toHaveLength(4);
  });

  test("filters traversal by relationship type", async () => {
    const { engine } = await createEngine();
    const result = await engine.traverse("project", {
      direction: "outgoing",
      relationshipTypes: ["owns"],
      maxDepth: 5,
    });

    expect(result.nodes).toHaveLength(1);
    expect(result.nodes[0].entity.id).toBe("repo");
  });

  test("supports zero-length paths and rejects invalid queries", async () => {
    const { engine } = await createEngine();
    const self = await engine.shortestPath("project", "project");
    expect(self).toMatchObject({ depth: 0, steps: [] });

    await expect(engine.traverse("missing")).rejects.toThrow("Entity not found");
    await expect(engine.traverse("project", { maxDepth: 21 })).rejects.toThrow("maxDepth");
  });
});
