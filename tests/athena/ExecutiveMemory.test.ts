import {
  ExecutiveMemory,
  InMemoryMemoryRepository,
} from "../../src/athena/memory";
import { AthenaDecision, AthenaRequest } from "../../src/athena";

describe("ExecutiveMemory", () => {
  it("persists a decision with request scope", async () => {
    const repository = new InMemoryMemoryRepository();
    const memory = new ExecutiveMemory(repository);
    const request: AthenaRequest = {
      id: "req-1",
      userId: "user-1",
      prompt: "Review Mor Logistics cash flow risk",
      timestamp: new Date("2026-07-19T00:00:00Z"),
      metadata: { project: "Polaris", organization: "Mor Logistics", priority: "high" },
    };
    const decision: AthenaDecision = {
      objective: "Assess cash flow risk",
      reasoning: ["Receivables are the primary exposure."],
      evidence: [],
      assumptions: [],
      missingInformation: ["Current aging report"],
      confidence: 0.8,
      nextActions: ["Review aged receivables"],
    };

    const saved = await memory.rememberDecision({ request, decision });
    const stored = await repository.getById(saved.id, request.userId);

    expect(stored?.scope.organization).toBe("Mor Logistics");
    expect(stored?.kind).toBe("decision");
    expect(stored?.content).toContain("Review aged receivables");
  });

  it("ranks relevant recent memories above unrelated memories", async () => {
    const repository = new InMemoryMemoryRepository();
    const memory = new ExecutiveMemory(repository);
    await repository.save({
      id: "relevant",
      kind: "decision",
      scope: { userId: "user-1", organization: "Mor Logistics" },
      title: "Cash flow review",
      content: "Receivables and customer payment delays",
      tags: ["cash", "flow", "receivables"],
      createdAt: new Date("2026-07-18T00:00:00Z"),
      updatedAt: new Date("2026-07-18T00:00:00Z"),
      importance: 0.8,
    });
    await repository.save({
      id: "unrelated",
      kind: "meeting",
      scope: { userId: "user-1" },
      title: "Office supplies",
      content: "Order printer paper",
      tags: ["office"],
      createdAt: new Date("2026-01-01T00:00:00Z"),
      updatedAt: new Date("2026-01-01T00:00:00Z"),
      importance: 0.2,
    });

    const snapshot = await memory.retrieve({
      userId: "user-1",
      text: "cash flow receivables",
      now: new Date("2026-07-19T00:00:00Z"),
    });

    expect(snapshot.matches[0].record.id).toBe("relevant");
    expect(snapshot.matches[0].score).toBeGreaterThan(snapshot.matches[1].score);
  });

  it("updates a memory while preserving its identity and creation time", async () => {
    const repository = new InMemoryMemoryRepository();
    const memory = new ExecutiveMemory(repository);
    const createdAt = new Date("2026-07-01T00:00:00Z");
    await repository.save({
      id: "decision:atlas",
      kind: "decision",
      scope: { userId: "user-1", project: "Polaris" },
      title: "Build Atlas",
      content: "Atlas follows Executive Memory.",
      tags: ["atlas"],
      createdAt,
      updatedAt: createdAt,
      importance: 0.7,
    });

    const updated = await memory.updateMemory("decision:atlas", {
      userId: "user-1",
      content: "Atlas follows Executive Memory because relationships require durable context.",
      tags: ["atlas", "memory", "atlas"],
      importance: 1.5,
      now: new Date("2026-07-19T00:00:00Z"),
    });

    expect(updated?.id).toBe("decision:atlas");
    expect(updated?.createdAt).toEqual(createdAt);
    expect(updated?.updatedAt).toEqual(new Date("2026-07-19T00:00:00Z"));
    expect(updated?.tags).toEqual(["atlas", "memory"]);
    expect(updated?.importance).toBe(1);
  });

  it("prevents one user from reading, updating, or deleting another user's memory", async () => {
    const repository = new InMemoryMemoryRepository();
    const memory = new ExecutiveMemory(repository);
    await repository.save({
      id: "private-memory",
      kind: "fact",
      scope: { userId: "owner" },
      title: "Private fact",
      content: "Only the owner may access this memory.",
      tags: ["private"],
      createdAt: new Date("2026-07-19T00:00:00Z"),
      updatedAt: new Date("2026-07-19T00:00:00Z"),
      importance: 0.5,
    });

    expect(await repository.getById("private-memory", "other-user")).toBeUndefined();
    expect(
      await memory.updateMemory("private-memory", {
        userId: "other-user",
        title: "Compromised",
      }),
    ).toBeUndefined();
    expect(await memory.forgetMemory("private-memory", "other-user")).toBe(false);
    expect(await repository.getById("private-memory", "owner")).toBeDefined();
  });

  it("forgets a memory only within the owning user scope", async () => {
    const repository = new InMemoryMemoryRepository();
    const memory = new ExecutiveMemory(repository);
    await repository.save({
      id: "obsolete",
      kind: "task",
      scope: { userId: "user-1" },
      title: "Obsolete task",
      content: "Remove after completion.",
      tags: ["obsolete"],
      createdAt: new Date("2026-07-19T00:00:00Z"),
      updatedAt: new Date("2026-07-19T00:00:00Z"),
      importance: 0.2,
    });

    expect(await memory.forgetMemory("obsolete", "user-1")).toBe(true);
    expect(await repository.getById("obsolete", "user-1")).toBeUndefined();
  });
});
