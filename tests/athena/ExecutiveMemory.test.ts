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
    const stored = await repository.getById(saved.id);

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
});
