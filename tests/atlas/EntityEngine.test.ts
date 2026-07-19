import {
  EntityFactory,
  EntityValidationError,
  InMemoryEntityRepository,
} from "../../src/atlas";

describe("Atlas Entity Engine", () => {
  const now = new Date("2026-07-19T12:00:00.000Z");

  it("creates a normalized, versioned entity", () => {
    const entity = EntityFactory.create({
      id: "project-polaris",
      type: "project",
      name: "  Polaris  ",
      tags: ["atlas", "atlas", " knowledge "],
      metadata: { owner: "Polaris Lab" },
      now,
    });

    expect(entity).toMatchObject({
      id: "project-polaris",
      type: "project",
      name: "Polaris",
      tags: ["atlas", "knowledge"],
      status: "active",
      version: 1,
    });
    expect(entity.createdAt).toEqual(now);
    expect(entity.updatedAt).toEqual(now);
  });

  it("rejects invalid entity names", () => {
    expect(() =>
      EntityFactory.create({ type: "document", name: "   " }),
    ).toThrow(EntityValidationError);
  });

  it("stores and retrieves defensive copies", async () => {
    const repository = new InMemoryEntityRepository();
    const entity = EntityFactory.create({
      id: "adr-003",
      type: "adr",
      name: "Executive Memory Architecture",
      metadata: { accepted: true },
      tags: ["architecture"],
      now,
    });

    await repository.save(entity);
    const found = await repository.findById(entity.id);
    expect(found).toEqual(entity);

    found!.tags.push("mutated");
    found!.metadata.accepted = false;

    const stored = await repository.findById(entity.id);
    expect(stored!.tags).toEqual(["architecture"]);
    expect(stored!.metadata).toEqual({ accepted: true });
  });

  it("lists entities by type", async () => {
    const repository = new InMemoryEntityRepository();
    await repository.save(
      EntityFactory.create({ id: "p1", type: "project", name: "Polaris" }),
    );
    await repository.save(
      EntityFactory.create({ id: "d1", type: "document", name: "Charter" }),
    );

    const projects = await repository.findByType("project");
    expect(projects).toHaveLength(1);
    expect(projects[0].id).toBe("p1");
  });

  it("updates an entity without changing its identity", async () => {
    const repository = new InMemoryEntityRepository();
    const original = EntityFactory.create({
      id: "release-v0.5.0",
      type: "release",
      name: "Executive Memory",
      now,
    });
    await repository.save(original);

    const updatedAt = new Date("2026-07-19T13:00:00.000Z");
    const updated = await repository.update(original.id, {
      name: "Executive Memory v0.5.0",
      status: "archived",
      now: updatedAt,
    });

    expect(updated.id).toBe(original.id);
    expect(updated.type).toBe(original.type);
    expect(updated.createdAt).toEqual(original.createdAt);
    expect(updated.updatedAt).toEqual(updatedAt);
    expect(updated.version).toBe(2);
    expect(updated.status).toBe("archived");
  });

  it("deletes entities", async () => {
    const repository = new InMemoryEntityRepository();
    const entity = EntityFactory.create({ type: "task", name: "Build Atlas" });
    await repository.save(entity);

    expect(await repository.delete(entity.id)).toBe(true);
    expect(await repository.findById(entity.id)).toBeUndefined();
    expect(await repository.delete(entity.id)).toBe(false);
  });
});
