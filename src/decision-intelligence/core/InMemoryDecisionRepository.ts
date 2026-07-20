import { Decision } from "./Decision";
import { DecisionStatus } from "./DecisionTypes";
import { DecisionRepository } from "./DecisionRepository";
import { DecisionValidator } from "./DecisionValidator";

export class InMemoryDecisionRepository implements DecisionRepository {
  private readonly items = new Map<string, Decision>();

  constructor(private readonly validator = new DecisionValidator()) {}

  async create(decision: Decision): Promise<Decision> {
    if (this.items.has(decision.id)) throw new Error(`Decision already exists: ${decision.id}`);
    this.validator.validate(decision);
    const clone = structuredClone(decision);
    this.items.set(clone.id, clone);
    return structuredClone(clone);
  }

  async getById(id: string): Promise<Decision | undefined> {
    const item = this.items.get(id);
    return item ? structuredClone(item) : undefined;
  }

  async list(status?: DecisionStatus): Promise<Decision[]> {
    return [...this.items.values()]
      .filter((item) => !status || item.status === status)
      .map((item) => structuredClone(item));
  }

  async update(decision: Decision): Promise<Decision> {
    const current = this.items.get(decision.id);
    if (!current) throw new Error(`Decision not found: ${decision.id}`);
    const next: Decision = {
      ...structuredClone(decision),
      createdAt: new Date(current.createdAt),
      updatedAt: new Date(),
      version: current.version + 1,
    };
    this.validator.validate(next);
    this.items.set(next.id, next);
    return structuredClone(next);
  }

  async delete(id: string): Promise<boolean> {
    return this.items.delete(id);
  }
}
