import { MemoryQuery, MemoryRecord } from "./types";

export interface MemoryRepository {
  save(record: MemoryRecord): Promise<void>;
  getById(id: string): Promise<MemoryRecord | undefined>;
  list(query: MemoryQuery): Promise<MemoryRecord[]>;
}
