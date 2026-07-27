import {
  QuickBooksApiClient,
  QuickBooksReportType,
  QuickBooksResourceType,
} from "./QuickBooksApiClient";

export interface QuickBooksVerificationClient extends QuickBooksApiClient {
  getVerificationStatus(): Readonly<Record<string, unknown>>;
}

export interface QuickBooksProductionVerificationRequest {
  readonly credentialReference: string;
  readonly resources?: readonly QuickBooksResourceType[];
  readonly reports?: readonly QuickBooksReportType[];
  readonly pageSize?: number;
  readonly maxPagesPerResource?: number;
  readonly disconnectAfter?: boolean;
  readonly signal?: AbortSignal;
}

export interface QuickBooksProductionVerificationResult {
  readonly status: "healthy" | "unhealthy";
  readonly companyName?: string;
  readonly checkedAt: string;
  readonly lastSuccessfulRequestAt?: string;
  readonly recordCounts: Readonly<Partial<Record<QuickBooksResourceType, number>>>;
  readonly reportAvailability: Readonly<Partial<Record<QuickBooksReportType, boolean>>>;
  readonly failures: readonly {
    readonly operation: string;
    readonly message: string;
  }[];
  readonly secretsExposed: false;
}

const DEFAULT_RESOURCES: readonly QuickBooksResourceType[] = [
  "company",
  "account",
  "customer",
  "vendor",
  "invoice",
  "payment",
  "bill",
  "purchase",
  "journal-entry",
];

const DEFAULT_REPORTS: readonly QuickBooksReportType[] = [
  "profit-and-loss",
  "balance-sheet",
  "cash-flow",
  "aged-receivables",
  "aged-payables",
];

/**
 * Performs a read-only production smoke verification without returning
 * credentials, tokens, realm IDs, or financial record payloads.
 */
export class QuickBooksProductionVerificationService {
  public constructor(
    private readonly client: QuickBooksVerificationClient,
    private readonly now: () => Date = () => new Date(),
  ) {}

  public async verify(
    request: QuickBooksProductionVerificationRequest,
  ): Promise<QuickBooksProductionVerificationResult> {
    const resources = request.resources ?? DEFAULT_RESOURCES;
    const reports = request.reports ?? DEFAULT_REPORTS;
    const pageSize = Math.min(Math.max(request.pageSize ?? 100, 1), 1000);
    const maxPages = Math.max(request.maxPagesPerResource ?? 1000, 1);
    const recordCounts: Partial<Record<QuickBooksResourceType, number>> = {};
    const reportAvailability: Partial<Record<QuickBooksReportType, boolean>> = {};
    const failures: Array<{ operation: string; message: string }> = [];

    try {
      await this.client.authenticate(request.credentialReference, request.signal);

      for (const resource of resources) {
        try {
          recordCounts[resource] = await this.countResource(
            resource,
            pageSize,
            maxPages,
            request.signal,
          );
        } catch (error) {
          recordCounts[resource] = 0;
          failures.push({
            operation: `resource:${resource}`,
            message: this.toSafeMessage(error),
          });
        }
      }

      for (const report of reports) {
        try {
          await this.client.report(report, undefined, request.signal);
          reportAvailability[report] = true;
        } catch (error) {
          reportAvailability[report] = false;
          failures.push({
            operation: `report:${report}`,
            message: this.toSafeMessage(error),
          });
        }
      }

      const health = await this.client.health(request.signal);
      const verification = this.client.getVerificationStatus();
      return {
        status: health.healthy && failures.length === 0 ? "healthy" : "unhealthy",
        companyName: this.asString(verification.companyName),
        checkedAt: this.now().toISOString(),
        lastSuccessfulRequestAt: this.asString(verification.lastSuccessfulRequestAt),
        recordCounts,
        reportAvailability,
        failures,
        secretsExposed: false,
      };
    } catch (error) {
      const verification = this.client.getVerificationStatus();
      return {
        status: "unhealthy",
        companyName: this.asString(verification.companyName),
        checkedAt: this.now().toISOString(),
        lastSuccessfulRequestAt: this.asString(verification.lastSuccessfulRequestAt),
        recordCounts,
        reportAvailability,
        failures: [{ operation: "authenticate", message: this.toSafeMessage(error) }],
        secretsExposed: false,
      };
    } finally {
      if (request.disconnectAfter ?? true) {
        await this.client.disconnect();
      }
    }
  }

  private async countResource(
    resource: QuickBooksResourceType,
    pageSize: number,
    maxPages: number,
    signal?: AbortSignal,
  ): Promise<number> {
    let cursor: string | undefined;
    let count = 0;
    let pages = 0;

    do {
      const page = await this.client.list(resource, undefined, cursor, pageSize, signal);
      count += page.records.length;
      cursor = page.nextCursor;
      pages += 1;
      if (cursor && pages >= maxPages) {
        throw new Error(`QuickBooks verification page limit reached for ${resource}`);
      }
    } while (cursor);

    return count;
  }

  private toSafeMessage(error: unknown): string {
    if (!(error instanceof Error)) return "QuickBooks verification failed";
    return error.message
      .replace(/Bearer\s+[A-Za-z0-9._~+\/-]+=*/gi, "Bearer [REDACTED]")
      .replace(/(client_secret|refresh_token|access_token|realmId)=([^&\s]+)/gi, "$1=[REDACTED]");
  }

  private asString(value: unknown): string | undefined {
    return typeof value === "string" ? value : undefined;
  }
}
