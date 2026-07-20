import { randomUUID } from "node:crypto";
import { CreateDecisionInput, Decision } from "./Decision";
import { DecisionValidator } from "./DecisionValidator";

export class DecisionFactory {
  constructor(
    private readonly validator = new DecisionValidator(),
    private readonly clock: () => Date = () => new Date(),
    private readonly idFactory: () => string = () => randomUUID(),
  ) {}

  create(input: CreateDecisionInput): Decision {
    this.validator.validateCreate(input);
    const now = this.clock();
    const decision: Decision = {
      id: input.id?.trim() || this.idFactory(),
      title: input.title.trim(),
      question: input.question.trim(),
      status: "draft",
      options: [],
      evidence: [],
      constraints: [],
      risks: [],
      tags: [...new Set((input.tags ?? []).map((tag) => tag.trim()).filter(Boolean))],
      metadata: structuredClone(input.metadata ?? {}),
      version: 1,
      createdAt: new Date(now),
      updatedAt: new Date(now),
    };
    this.validator.validate(decision);
    return decision;
  }
}
