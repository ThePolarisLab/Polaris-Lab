import { MemoryQuery, MemoryRecord } from "./types";

export interface MemoryRepository {
  save(record: MemoryRecord): Promise<void>;
  getById(id: string, userId: string): Promise<MemoryRecord | undefined>;
  list(query: MemoryQuery): Promise<MemoryRecord[]>;
  update(record: MemoryRecord): Promise<boolean>;
  delete(id: string, userId: string): Promise<boolean>;
}
