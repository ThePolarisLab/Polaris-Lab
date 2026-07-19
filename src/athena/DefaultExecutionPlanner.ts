import { ExecutionPlanner } from "./ports";
import { AthenaIntent, AthenaRequest, ExecutionPlan, ReasoningStep } from "./types";

function step(id: string, name: string): ReasoningStep {
  return { id, name, status: "pending" };
}

export class DefaultExecutionPlanner implements ExecutionPlanner {
  async createPlan(
    request: AthenaRequest,
    intent: AthenaIntent,
  ): Promise<ExecutionPlan> {
    const objective = request.prompt.trim();

    return {
      objective,
      intent,
      steps: [
        step("validate-request", "Validate request"),
        step("assemble-context", "Assemble relevant context"),
        step("retrieve-memory", "Retrieve relevant executive memory"),
        step("evaluate-evidence", "Evaluate evidence and assumptions"),
        step("form-decision", "Form structured decision"),
        step("build-response", "Build executive response"),
        step("persist-outcome", "Persist important outcome"),
      ],
    };
  }
}
