import { IRuntime } from "../core/IRuntime";
import { IWorker } from "../core/IWorker";

export class WorkerRegistry {
  private readonly workers = new Map<string, IWorker>();

  register<T extends IWorker>(worker: T): T {
    const name = worker.definition.name.trim();
    if (!name) throw new Error("Worker name is required.");
    if (this.workers.has(name)) throw new Error(`Worker '${name}' is already registered.`);
    this.workers.set(name, worker);
    return worker;
  }

  get(name: string): IWorker | undefined {
    return this.workers.get(name);
  }

  has(name: string): boolean {
    return this.workers.has(name);
  }

  list(): readonly IWorker[] {
    return Object.freeze([...this.workers.values()]);
  }

  install(runtime: IRuntime): void {
    for (const worker of this.workers.values()) runtime.register(worker);
  }
}
