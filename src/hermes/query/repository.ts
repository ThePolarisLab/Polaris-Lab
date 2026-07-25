import { AnyExecutiveEntity } from "../executive/contracts";
import { ExecutiveRepository } from "../executive/repository";
import {
  ExecutiveQuery,
  ExecutiveQueryRepository,
  PageResult,
  QueryContext,
  QueryFilter,
  SortExpression,
} from "./contracts";

const DEFAULT_LIMIT = 50;
const MAX_LIMIT = 500;

export class ExecutiveReadQueryRepository implements ExecutiveQueryRepository {
  constructor(private readonly repository: ExecutiveRepository) {}

  async search<T extends AnyExecutiveEntity>(context: QueryContext, query: ExecutiveQuery<T>): Promise<PageResult<T>> {
    assertContext(context);
    const offset = normalizeOffset(query.page?.offset);
    const limit = normalizeLimit(query.page?.limit);
    const source = await this.repository.listByKind<T>(query.kind);
    let matches = source.filter((entity) => entity.organizationId === context.organizationId);
    for (const filter of query.filters ?? []) matches = matches.filter((entity) => matchesFilter(entity, filter));
    if (query.predicate) matches = matches.filter(query.predicate);
    matches = stableSort(matches, query.sort ?? []);
    const items = Object.freeze(matches.slice(offset, offset + limit));
    return Object.freeze({ items, total: matches.length, offset, limit, hasMore: offset + items.length < matches.length });
  }

  async getById<T extends AnyExecutiveEntity>(context: QueryContext, id: string): Promise<T | undefined> {
    assertContext(context);
    const entity = await this.repository.getById<T>(id);
    return entity?.organizationId === context.organizationId ? entity : undefined;
  }

  async count<T extends AnyExecutiveEntity>(context: QueryContext, query: ExecutiveQuery<T>): Promise<number> {
    return (await this.search(context, { ...query, page: { offset: 0, limit: MAX_LIMIT } })).total;
  }

  async exists<T extends AnyExecutiveEntity>(context: QueryContext, query: ExecutiveQuery<T>): Promise<boolean> {
    return (await this.search(context, { ...query, page: { offset: 0, limit: 1 } })).total > 0;
  }
}

function assertContext(context: QueryContext): void {
  if (!context.organizationId.trim()) throw new Error("Query organization id is required");
}

function normalizeOffset(value = 0): number {
  if (!Number.isInteger(value) || value < 0) throw new Error("Query offset must be a non-negative integer");
  return value;
}

function normalizeLimit(value = DEFAULT_LIMIT): number {
  if (!Number.isInteger(value) || value < 1 || value > MAX_LIMIT) throw new Error(`Query limit must be between 1 and ${MAX_LIMIT}`);
  return value;
}

function readField(entity: AnyExecutiveEntity, path: string): unknown {
  return path.split(".").reduce<unknown>((value, segment) => {
    if (value === null || typeof value !== "object") return undefined;
    return (value as Record<string, unknown>)[segment];
  }, entity);
}

function matchesFilter(entity: AnyExecutiveEntity, filter: QueryFilter): boolean {
  const actual = readField(entity, filter.field);
  const expected = filter.value;
  switch (filter.operator) {
    case "eq": return actual === expected;
    case "neq": return actual !== expected;
    case "gt": return comparable(actual) > comparable(expected);
    case "gte": return comparable(actual) >= comparable(expected);
    case "lt": return comparable(actual) < comparable(expected);
    case "lte": return comparable(actual) <= comparable(expected);
    case "in": return Array.isArray(expected) && expected.includes(actual);
    case "contains": return typeof actual === "string" && typeof expected === "string" && actual.toLowerCase().includes(expected.toLowerCase());
  }
}

function comparable(value: unknown): number | string {
  if (typeof value === "number" || typeof value === "string") return value;
  return Number.NaN;
}

function stableSort<T extends AnyExecutiveEntity>(items: readonly T[], expressions: readonly SortExpression[]): T[] {
  return items.map((item, index) => ({ item, index })).sort((left, right) => {
    for (const expression of expressions) {
      const a = readField(left.item, expression.field);
      const b = readField(right.item, expression.field);
      const comparison = compare(a, b);
      if (comparison !== 0) return expression.direction === "asc" ? comparison : -comparison;
    }
    return left.index - right.index;
  }).map(({ item }) => item);
}

function compare(a: unknown, b: unknown): number {
  if (a === b) return 0;
  if (a === undefined || a === null) return 1;
  if (b === undefined || b === null) return -1;
  return comparable(a) < comparable(b) ? -1 : 1;
}
