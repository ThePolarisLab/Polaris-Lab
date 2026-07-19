import {
  InMemoryRelationshipRepository,
  RelationshipFactory,
  RelationshipValidator,
} from "../../src/atlas";

describe("Atlas Relationship Engine", () => {
  test("creates a normalized relationship", () => {
    const relationship = RelationshipFactory.create({
      id: " rel-1 ",
      sourceEntityId: " project-1 ",
      targetEntityId: " repo-1 ",
      type: "owns",
      confidence: 0.9,
      now: new Date("2026-07-19T12:00:00Z"),
    });

    expect(relationship.id).toBe("rel-1");
    expect(relationship.sourceEntityId).toBe("project-1");
    expect(relationship.targetEntityId).toBe("repo-1");
    expect(relationship.version).toBe(1);
  });

  test("rejects self relationships and invalid confidence", () => {
    expect(() => RelationshipFactory.create({
      sourceEntityId: "same",
      targetEntityId: "same",
      type: "contains",
    })).toThrow("self relationships");

    expect(() => RelationshipValidator.validateCreate({
      sourceEntityId: "a",
      targetEntityId: "b",
      type: "contains",
      confidence: 2,
    })).toThrow("between 0 and 1");
  });

  test("stores defensive copies and filters relationships", async () => {
    const repository = new InMemoryRelationshipRepository();
    const relationship = RelationshipFactory.create({
      id: "rel-2",
      sourceEntityId: "project-1",
      targetEntityId: "adr-4",
      type: "documents",
      metadata: { reason: "architecture" },
    });

    await repository.save(relationship);
    relationship.metadata.reason = "mutated";

    const stored = await repository.getById("rel-2");
    expect(stored?.metadata.reason).toBe("architecture");
    expect(await repository.list({ sourceEntityId: "project-1" })).toHaveLength(1);
    expect(await repository.list({ types: ["owns"] })).toHaveLength(0);
  });

  test("updates version and deletes a relationship", async () => {
    const repository = new InMemoryRelationshipRepository();
    await repository.save(RelationshipFactory.create({
      id: "rel-3",
      sourceEntityId: "component-1",
      targetEntityId: "system-1",
      type: "part_of",
    }));

    const updated = await repository.update("rel-3", {
      confidence: 0.75,
      status: "inactive",
      now: new Date("2026-07-19T13:00:00Z"),
    });

    expect(updated.version).toBe(2);
    expect(updated.confidence).toBe(0.75);
    expect(updated.status).toBe("inactive");
    expect(await repository.delete("rel-3")).toBe(true);
    expect(await repository.getById("rel-3")).toBeUndefined();
  });
});
