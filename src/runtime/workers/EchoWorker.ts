import { defineWorker } from "../sdk/WorkerFactory";

export const EchoWorker = defineWorker<string, string>({
  name: "echo",
  version: "1.0.0",
  description: "Reference Worker SDK worker.",
  defaultPayload: "Polaris",
  handler: (_context, payload) => payload,
});
