import { AnyExecutiveEntity, ExecutiveEntityKind } from "../executive/contracts";

export type QueryOperator = "eq" | "neq" | "gt" | "gte" | "lt" | "lte" | "in" | "contains";

export interface QueryFilter {
  readonly field: string;
  readonly operator: QueryOperator;
  readonly value: unknown;
}

export interface SortExpression {
  readonly field: string;
  readonly direction: "asc" | "desc";
}

export interface PageRequest {
  readonly offset?: number;
  readonly limit?: number;
}

export interface QueryContext {
  readonly organizationId: string;
}

export interface ExecutiveQuery<T extends AnyExecutiveEntity = AnyExecutiveEntity> {
  readonly kind: ExecutiveEntityKind;
  readonly filters?: readonly QueryFilter[];
  readonly sort?: readonly SortExpression[];
  readonly page?: PageRequest;
  readonly predicate?: (entity: T) => boolean;
}

export interface PageResult<T> {
  readonly items: readonly T[];
  readonly total: number;
  readonly offset: number;
  readonly limit: number;
  readonly hasMore: boolean;
}

export interface ExecutiveQueryRepository {
  search<T extends AnyExecutiveEntity>(context: QueryContext, query: ExecutiveQuery<T>): Promise<PageResult<T>>;
  getById<T extends AnyExecutiveEntity>(context: QueryContext, id: string): Promise<T | undefined>;
  count<T extends AnyExecutiveEntity>(context: QueryContext, query: ExecutiveQuery<T>): Promise<number>;
  exists<T extends AnyExecutiveEntity>(context: QueryContext, query: ExecutiveQuery<T>): Promise<boolean>;
}
