import {
  InMemoryEntityRepository,
  InMemoryRelationshipRepository,
  KnowledgeGraph,
} from "../../src/atlas";

describe("Atlas Knowledge Graph Core", () => {
  const createGraph = () => new KnowledgeGraph(
    new InMemoryEntityRepository(),
    new InMemoryRelationshipRepository(),
  );

  test("creates connected entities and returns neighbors", async () => {
    const graph = createGraph();
    await graph.addEntity({ id: "project-1", type: "project", name: "Atlas" });
    await graph.addEntity({ id: "repo-1", type: "repository", name: "Polaris-Lab" });
    await graph.addRelationship({
      id: "rel-1",
      sourceEntityId: "project-1",
      targetEntityId: "repo-1",
      type: "owns",
    });

    const outgoing = await graph.neighbors("project-1", { direction: "outgoing" });
    expect(outgoing).toHaveLength(1);
    expect(outgoing[0].entity.id).toBe("repo-1");
    expect(outgoing[0].direction).toBe("outgoing");

    const incoming = await graph.neighbors("repo-1", { direction: "incoming" });
    expect(incoming[0].entity.id).toBe("project-1");
  });

  test("rejects relationships whose endpoints do not exist", async () => {
    const graph = createGraph();
    await graph.addEntity({ id: "project-1", type: "project", name: "Atlas" });

    await expect(graph.addRelationship({
      sourceEntityId: "project-1",
      targetEntityId: "missing",
      type: "depends_on",
    })).rejects.toThrow("Target entity not found");
  });

  test("filters neighbors by relationship type", async () => {
    const graph = createGraph();
    await graph.addEntity({ id: "project", type: "project", name: "Atlas" });
    await graph.addEntity({ id: "repo", type: "repository", name: "Repo" });
    await graph.addEntity({ id: "adr", type: "adr", name: "ADR-006" });
    await graph.addRelationship({ sourceEntityId: "project", targetEntityId: "repo", type: "owns" });
    await graph.addRelationship({ sourceEntityId: "project", targetEntityId: "adr", type: "documents" });

    const matches = await graph.neighbors("project", { relationshipTypes: ["documents"] });
    expect(matches).toHaveLength(1);
    expect(matches[0].entity.id).toBe("adr");
  });

  test("prevents dangling relationships when deleting an entity", async () => {
    const graph = createGraph();
    await graph.addEntity({ id: "project", type: "project", name: "Atlas" });
    await graph.addEntity({ id: "repo", type: "repository", name: "Repo" });
    const relationship = await graph.addRelationship({
      sourceEntityId: "project",
      targetEntityId: "repo",
      type: "owns",
    });

    await expect(graph.removeEntity("project")).rejects.toThrow("Cannot delete entity with relationships");
    await graph.removeRelationship(relationship.id);
    await expect(graph.removeEntity("project")).resolves.toBe(true);
  });

  test("returns a consistent graph snapshot", async () => {
    const graph = createGraph();
    await graph.addEntity({ id: "project", type: "project", name: "Atlas" });
    await graph.addEntity({ id: "release", type: "release", name: "v0.6.0" });
    await graph.addRelationship({ sourceEntityId: "project", targetEntityId: "release", type: "produces" });

    const snapshot = await graph.snapshot();
    expect(snapshot.entities).toHaveLength(2);
    expect(snapshot.relationships).toHaveLength(1);
  });
});
