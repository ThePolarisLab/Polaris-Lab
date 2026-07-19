import { MemoryService } from "../ports";
import { AthenaDecision, AthenaRequest } from "../types";
import { ExecutiveMemory } from "./ExecutiveMemory";

export class AthenaMemoryAdapter implements MemoryService {
  constructor(private readonly memory: ExecutiveMemory) {}

  async remember(request: AthenaRequest, decision: AthenaDecision): Promise<void> {
    await this.memory.rememberDecision({ request, decision });
  }
}
