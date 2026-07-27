import {
  QuickBooksApiClient,
  QuickBooksPage,
  QuickBooksRecord,
  QuickBooksReportType,
  QuickBooksResourceType,
} from "./QuickBooksApiClient";

export interface QuickBooksCredential {
  readonly clientId: string;
  readonly clientSecret: string;
  readonly refreshToken: string;
  readonly realmId: string;
}

export interface QuickBooksCredentialResolver {
  resolve(reference: string, signal?: AbortSignal): Promise<QuickBooksCredential>;
}

export interface IntuitQuickBooksApiClientOptions {
  readonly credentialResolver: QuickBooksCredentialResolver;
  readonly expectedCompanyName: string;
  readonly apiBaseUrl?: string;
  readonly tokenUrl?: string;
  readonly minorVersion?: string;
  readonly maxAttempts?: number;
  readonly baseDelayMs?: number;
  readonly fetchImplementation?: typeof fetch;
  readonly now?: () => number;
  readonly sleep?: (delayMs: number) => Promise<void>;
}

interface TokenState {
  readonly accessToken: string;
  readonly refreshToken: string;
  readonly expiresAt: number;
}

interface IntuitTokenResponse {
  readonly access_token?: string;
  readonly refresh_token?: string;
  readonly expires_in?: number;
  readonly error?: string;
  readonly error_description?: string;
}

interface IntuitQueryResponse {
  readonly QueryResponse?: Readonly<Record<string, unknown>>;
  readonly time?: string;
}

const RESOURCE_ENTITY: Readonly<Record<QuickBooksResourceType, string>> = {
  company: "CompanyInfo",
  customer: "Customer",
  vendor: "Vendor",
  account: "Account",
  invoice: "Invoice",
  payment: "Payment",
  bill: "Bill",
  purchase: "Purchase",
  "journal-entry": "JournalEntry",
};

const REPORT_NAME: Readonly<Record<QuickBooksReportType, string>> = {
  "profit-and-loss": "ProfitAndLoss",
  "balance-sheet": "BalanceSheet",
  "cash-flow": "CashFlow",
  "aged-receivables": "AgedReceivables",
  "aged-payables": "AgedPayables",
};

export class QuickBooksProductionError extends Error {
  public constructor(
    message: string,
    public readonly code: string,
    public readonly status?: number,
    public readonly retryable = false,
  ) {
    super(message);
    this.name = "QuickBooksProductionError";
  }
}

export class IntuitQuickBooksApiClient implements QuickBooksApiClient {
  private readonly fetchImplementation: typeof fetch;
  private readonly apiBaseUrl: string;
  private readonly tokenUrl: string;
  private readonly minorVersion: string;
  private readonly maxAttempts: number;
  private readonly baseDelayMs: number;
  private readonly now: () => number;
  private readonly sleep: (delayMs: number) => Promise<void>;
  private credential?: QuickBooksCredential;
  private token?: TokenState;
  private connectedCompanyName?: string;
  private lastSuccessfulRequestAt?: string;

  public constructor(private readonly options: IntuitQuickBooksApiClientOptions) {
    this.fetchImplementation = options.fetchImplementation ?? fetch;
    this.apiBaseUrl = (options.apiBaseUrl ?? "https://quickbooks.api.intuit.com").replace(/\/$/, "");
    this.tokenUrl = options.tokenUrl ?? "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer";
    this.minorVersion = options.minorVersion ?? "75";
    this.maxAttempts = Math.max(1, options.maxAttempts ?? 3);
    this.baseDelayMs = Math.max(0, options.baseDelayMs ?? 250);
    this.now = options.now ?? Date.now;
    this.sleep = options.sleep ?? ((delayMs) => new Promise((resolve) => setTimeout(resolve, delayMs)));
  }

  public async authenticate(credentialReference?: string, signal?: AbortSignal): Promise<void> {
    if (!credentialReference) {
      throw new QuickBooksProductionError(
        "QuickBooks credential reference is required",
        "QBO_CREDENTIAL_REFERENCE_REQUIRED",
      );
    }

    this.credential = await this.options.credentialResolver.resolve(credentialReference, signal);
    this.validateCredential(this.credential);
    await this.refreshAccessToken(signal);

    const company = await this.getCompanyInfo(signal);
    const companyName = this.extractCompanyName(company);
    if (companyName !== this.options.expectedCompanyName) {
      this.clearSession();
      throw new QuickBooksProductionError(
        `QuickBooks company identity mismatch: expected ${this.options.expectedCompanyName}`,
        "QBO_COMPANY_MISMATCH",
      );
    }
    this.connectedCompanyName = companyName;
  }

  public async list(
    resource: QuickBooksResourceType,
    changedSince?: string,
    cursor?: string,
    limit?: number,
    signal?: AbortSignal,
  ): Promise<QuickBooksPage> {
    this.assertAuthenticated();
    if (resource === "company") {
      const company = await this.getCompanyInfo(signal);
      return { records: [this.toRecord(company)], observedAt: this.lastSuccessfulRequestAt };
    }

    const entity = RESOURCE_ENTITY[resource];
    const startPosition = this.parseCursor(cursor);
    const pageSize = Math.min(Math.max(limit ?? 100, 1), 1000);
    const where = changedSince
      ? ` WHERE MetaData.LastUpdatedTime > '${this.escapeQueryLiteral(changedSince)}'`
      : "";
    const query = `SELECT * FROM ${entity}${where} STARTPOSITION ${startPosition} MAXRESULTS ${pageSize}`;
    const payload = await this.requestJson<IntuitQueryResponse>(
      `/v3/company/${this.credential!.realmId}/query?query=${encodeURIComponent(query)}&minorversion=${this.minorVersion}`,
      { method: "GET", signal },
    );
    const records = this.extractQueryRecords(payload, entity).map((item) => this.toRecord(item));
    const nextCursor = records.length === pageSize ? String(startPosition + pageSize) : undefined;
    return { records, nextCursor, observedAt: payload.time ?? this.lastSuccessfulRequestAt };
  }

  public async report(
    report: QuickBooksReportType,
    changedSince?: string,
    signal?: AbortSignal,
  ): Promise<QuickBooksRecord> {
    this.assertAuthenticated();
    const params = new URLSearchParams({ minorversion: this.minorVersion });
    if (changedSince) params.set("start_date", changedSince.slice(0, 10));
    const payload = await this.requestJson<Record<string, unknown>>(
      `/v3/company/${this.credential!.realmId}/reports/${REPORT_NAME[report]}?${params.toString()}`,
      { method: "GET", signal },
    );
    return {
      id: `${report}:${this.lastSuccessfulRequestAt ?? new Date(this.now()).toISOString()}`,
      updatedAt: this.lastSuccessfulRequestAt,
      report,
      data: payload,
    };
  }

  public async health(signal?: AbortSignal): Promise<{ readonly healthy: boolean; readonly message?: string }> {
    try {
      this.assertAuthenticated();
      const company = await this.getCompanyInfo(signal);
      const companyName = this.extractCompanyName(company);
      const healthy = companyName === this.options.expectedCompanyName;
      return {
        healthy,
        message: healthy
          ? `Connected to ${companyName}`
          : "QuickBooks company identity verification failed",
      };
    } catch (error) {
      return {
        healthy: false,
        message: error instanceof Error ? error.message : "QuickBooks health check failed",
      };
    }
  }

  public async disconnect(): Promise<void> {
    this.clearSession();
  }

  public getVerificationStatus(): Readonly<Record<string, unknown>> {
    return {
      authenticated: Boolean(this.token),
      companyName: this.connectedCompanyName,
      lastSuccessfulRequestAt: this.lastSuccessfulRequestAt,
      secretsExposed: false,
    };
  }

  private async getCompanyInfo(signal?: AbortSignal): Promise<Record<string, unknown>> {
    this.assertAuthenticated();
    const payload = await this.requestJson<Record<string, unknown>>(
      `/v3/company/${this.credential!.realmId}/companyinfo/${this.credential!.realmId}?minorversion=${this.minorVersion}`,
      { method: "GET", signal },
    );
    const company = payload.CompanyInfo;
    if (!company || typeof company !== "object") {
      throw new QuickBooksProductionError("QuickBooks company information was missing", "QBO_COMPANY_INFO_MISSING");
    }
    return company as Record<string, unknown>;
  }

  private async requestJson<T>(path: string, init: RequestInit): Promise<T> {
    let lastError: unknown;
    for (let attempt = 1; attempt <= this.maxAttempts; attempt += 1) {
      try {
        await this.ensureAccessToken(init.signal);
        const response = await this.fetchImplementation(`${this.apiBaseUrl}${path}`, {
          ...init,
          headers: {
            Accept: "application/json",
            Authorization: `Bearer ${this.token!.accessToken}`,
            ...(init.headers ?? {}),
          },
        });

        if (response.status === 401 && attempt < this.maxAttempts) {
          await this.refreshAccessToken(init.signal);
          continue;
        }
        if (response.ok) {
          this.lastSuccessfulRequestAt = new Date(this.now()).toISOString();
          return await response.json() as T;
        }

        const retryable = response.status === 429 || response.status >= 500;
        const error = new QuickBooksProductionError(
          `QuickBooks request failed with status ${response.status}`,
          response.status === 429 ? "QBO_RATE_LIMITED" : "QBO_REQUEST_FAILED",
          response.status,
          retryable,
        );
        if (!retryable || attempt === this.maxAttempts) throw error;
        lastError = error;
        await this.sleep(this.retryDelay(attempt, response.headers.get("retry-after")));
      } catch (error) {
        lastError = error;
        if (error instanceof QuickBooksProductionError && !error.retryable) throw error;
        if (attempt === this.maxAttempts) break;
        await this.sleep(this.retryDelay(attempt));
      }
    }

    throw lastError instanceof Error
      ? lastError
      : new QuickBooksProductionError("QuickBooks request failed", "QBO_REQUEST_FAILED");
  }

  private async ensureAccessToken(signal?: AbortSignal): Promise<void> {
    this.assertAuthenticated();
    if (this.token!.expiresAt - this.now() <= 60_000) await this.refreshAccessToken(signal);
  }

  private async refreshAccessToken(signal?: AbortSignal): Promise<void> {
    if (!this.credential) {
      throw new QuickBooksProductionError("QuickBooks credentials are unavailable", "QBO_NOT_AUTHENTICATED");
    }
    const basic = Buffer.from(`${this.credential.clientId}:${this.credential.clientSecret}`).toString("base64");
    const refreshToken = this.token?.refreshToken ?? this.credential.refreshToken;
    const response = await this.fetchImplementation(this.tokenUrl, {
      method: "POST",
      signal,
      headers: {
        Accept: "application/json",
        Authorization: `Basic ${basic}`,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({ grant_type: "refresh_token", refresh_token: refreshToken }).toString(),
    });
    const payload = await response.json() as IntuitTokenResponse;
    if (!response.ok || !payload.access_token) {
      throw new QuickBooksProductionError(
        payload.error_description ?? "QuickBooks token refresh failed",
        payload.error ?? "QBO_TOKEN_REFRESH_FAILED",
        response.status,
      );
    }
    this.token = {
      accessToken: payload.access_token,
      refreshToken: payload.refresh_token ?? refreshToken,
      expiresAt: this.now() + Math.max(60, payload.expires_in ?? 3600) * 1000,
    };
  }

  private extractCompanyName(company: Record<string, unknown>): string | undefined {
    const value = company.CompanyName ?? company.LegalName;
    return typeof value === "string" ? value : undefined;
  }

  private extractQueryRecords(payload: IntuitQueryResponse, entity: string): readonly Record<string, unknown>[] {
    const value = payload.QueryResponse?.[entity];
    return Array.isArray(value)
      ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
      : [];
  }

  private toRecord(value: Record<string, unknown>): QuickBooksRecord {
    const metadata = value.MetaData && typeof value.MetaData === "object"
      ? value.MetaData as Record<string, unknown>
      : undefined;
    const id = value.Id;
    if (typeof id !== "string" && typeof id !== "number") {
      throw new QuickBooksProductionError("QuickBooks record is missing an Id", "QBO_RECORD_ID_MISSING");
    }
    return {
      ...value,
      id: String(id),
      updatedAt: typeof metadata?.LastUpdatedTime === "string" ? metadata.LastUpdatedTime : undefined,
    };
  }

  private parseCursor(cursor?: string): number {
    if (!cursor) return 1;
    const parsed = Number.parseInt(cursor, 10);
    if (!Number.isFinite(parsed) || parsed < 1) {
      throw new QuickBooksProductionError("QuickBooks cursor is invalid", "QBO_CURSOR_INVALID");
    }
    return parsed;
  }

  private escapeQueryLiteral(value: string): string {
    return value.replace(/'/g, "\\'");
  }

  private retryDelay(attempt: number, retryAfter?: string | null): number {
    const retryAfterSeconds = retryAfter ? Number.parseInt(retryAfter, 10) : Number.NaN;
    if (Number.isFinite(retryAfterSeconds) && retryAfterSeconds >= 0) return retryAfterSeconds * 1000;
    return this.baseDelayMs * (2 ** (attempt - 1));
  }

  private validateCredential(credential: QuickBooksCredential): void {
    for (const [name, value] of Object.entries(credential)) {
      if (!value || typeof value !== "string") {
        throw new QuickBooksProductionError(`QuickBooks credential field ${name} is missing`, "QBO_CREDENTIAL_INVALID");
      }
    }
  }

  private assertAuthenticated(): void {
    if (!this.credential || !this.token) {
      throw new QuickBooksProductionError("QuickBooks client is not authenticated", "QBO_NOT_AUTHENTICATED");
    }
  }

  private clearSession(): void {
    this.credential = undefined;
    this.token = undefined;
    this.connectedCompanyName = undefined;
    this.lastSuccessfulRequestAt = undefined;
  }
}
