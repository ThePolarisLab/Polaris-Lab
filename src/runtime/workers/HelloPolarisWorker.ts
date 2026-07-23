import { ExecutionContext } from "../core/ExecutionContext";
import { IWorker } from "../core/IWorker";
import { WorkerDefinition } from "../core/WorkerDefinition";
import { WorkerResult } from "../core/WorkerResult";

export class HelloPolarisWorker implements IWorker<string> {
  readonly definition: WorkerDefinition = {
    name: "hello-polaris",
    version: "1.0.0",
    description: "Reference worker proving Runtime execution.",
  };

  async execute(context: ExecutionContext): Promise<WorkerResult<string>> {
    context.logger.info("Hello Polaris", {
      jobId: context.jobId,
      correlationId: context.correlationId,
    });

    return WorkerResult.success("Hello Polaris");
  }
}
