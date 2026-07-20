import { Decision, DecisionStatus } from "./Decision";

export interface DecisionRepository {
  create(decision: Decision): Promise<Decision>;
  getById(id: string): Promise<Decision | undefined>;
  list(status?: DecisionStatus): Promise<Decision[]>;
  update(decision: Decision): Promise<Decision>;
  delete(id: string): Promise<boolean>;
}
