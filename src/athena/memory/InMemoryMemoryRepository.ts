import { MemoryRepository } from "./MemoryRepository";
import { MemoryQuery, MemoryRecord } from "./types";

export class InMemoryMemoryRepository implements MemoryRepository {
  private readonly records = new Map<string, MemoryRecord>();

  async save(record: MemoryRecord): Promise<void> {
    this.records.set(record.id, this.clone(record));
  }

  async getById(id: string, userId: string): Promise<MemoryRecord | undefined> {
    const record = this.records.get(id);
    if (!record || record.scope.userId !== userId) return undefined;
    return this.clone(record);
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
      .map((record) => this.clone(record));
  }

  async update(record: MemoryRecord): Promise<boolean> {
    const existing = this.records.get(record.id);
    if (!existing || existing.scope.userId !== record.scope.userId) return false;
    this.records.set(record.id, this.clone(record));
    return true;
  }

  async delete(id: string, userId: string): Promise<boolean> {
    const existing = this.records.get(id);
    if (!existing || existing.scope.userId !== userId) return false;
    return this.records.delete(id);
  }

  private clone(record: MemoryRecord): MemoryRecord {
    return {
      ...record,
      scope: { ...record.scope },
      tags: [...record.tags],
      createdAt: new Date(record.createdAt),
      updatedAt: new Date(record.updatedAt),
      metadata: record.metadata ? { ...record.metadata } : undefined,
    };
  }
}
