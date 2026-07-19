import { MemoryRepository } from "./MemoryRepository";
import { MemoryQuery, MemoryRecord } from "./types";

export class InMemoryMemoryRepository implements MemoryRepository {
  private readonly records = new Map<string, MemoryRecord>();

  async save(record: MemoryRecord): Promise<void> {
    this.records.set(record.id, { ...record, tags: [...record.tags] });
  }

  async getById(id: string): Promise<MemoryRecord | undefined> {
    const record = this.records.get(id);
    return record ? { ...record, tags: [...record.tags] } : undefined;
  }

  async list(query: MemoryQuery): Promise<MemoryRecord[]> {
    return [...this.records.values()]
      .filter((record) => record.scope.userId === query.userId)
      .filter((record) => !query.kinds?.length || query.kinds.includes(record.kind))
      .filter((record) => !query.project || record.scope.project === query.project)
      .filter(
        (record) =>
          !query.organization || record.scope.organization === query.organization,
      )
      .filter(
        (record) =>
          !query.tags?.length || query.tags.every((tag) => record.tags.includes(tag)),
      )
      .map((record) => ({ ...record, tags: [...record.tags] }));
  }
}
