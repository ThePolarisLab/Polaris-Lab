export type QuickBooksResourceType =
  | "company"
  | "customer"
  | "vendor"
  | "account"
  | "invoice"
  | "payment"
  | "bill"
  | "purchase"
  | "journal-entry";

export type QuickBooksReportType =
  | "profit-and-loss"
  | "balance-sheet"
  | "cash-flow"
  | "aged-receivables"
  | "aged-payables";

export interface QuickBooksRecord {
  readonly id: string;
  readonly updatedAt?: string;
  readonly [key: string]: unknown;
}

export interface QuickBooksPage {
  readonly records: readonly QuickBooksRecord[];
  readonly nextCursor?: string;
  readonly observedAt?: string;
}

export interface QuickBooksApiClient {
  authenticate(credentialReference?: string, signal?: AbortSignal): Promise<void>;
  list(
    resource: QuickBooksResourceType,
    changedSince?: string,
    cursor?: string,
    limit?: number,
    signal?: AbortSignal,
  ): Promise<QuickBooksPage>;
  report(
    report: QuickBooksReportType,
    changedSince?: string,
    signal?: AbortSignal,
  ): Promise<QuickBooksRecord>;
  health(signal?: AbortSignal): Promise<{ readonly healthy: boolean; readonly message?: string }>;
  disconnect(): Promise<void>;
}
