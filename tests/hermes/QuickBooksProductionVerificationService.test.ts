import {
  QuickBooksPage,
  QuickBooksProductionVerificationService,
  QuickBooksRecord,
  QuickBooksReportType,
  QuickBooksResourceType,
  QuickBooksVerificationClient,
} from "../../src/hermes/connectors/quickbooks";

class FakeVerificationClient implements QuickBooksVerificationClient {
  public disconnected = false;
  public readonly cursors: Array<string | undefined> = [];
  public failReport?: QuickBooksReportType;
  public failAuthentication = false;

  public async authenticate(reference?: string): Promise<void> {
    if (this.failAuthentication) throw new Error("access_token=secret-value");
    if (reference !== "secret://qbo") throw new Error("unexpected reference");
  }

  public async list(
    resource: QuickBooksResourceType,
    _changedSince?: string,
    cursor?: string,
  ): Promise<QuickBooksPage> {
    this.cursors.push(cursor);
    if (resource === "invoice" && !cursor) {
      return { records: [{ id: "invoice-1" }], nextCursor: "2" };
    }
    if (resource === "invoice") {
      return { records: [{ id: "invoice-2" }] };
    }
    return { records: [{ id: `${resource}-1` }] };
  }

  public async report(report: QuickBooksReportType): Promise<QuickBooksRecord> {
    if (report === this.failReport) throw new Error("report unavailable");
    return { id: report };
  }

  public async health(): Promise<{ healthy: boolean; message?: string }> {
    return { healthy: true, message: "Connected" };
  }

  public async disconnect(): Promise<void> {
    this.disconnected = true;
  }

  public getVerificationStatus(): Readonly<Record<string, unknown>> {
    return {
      companyName: "MOR LOGISTICS MANITOBA LIMITED",
      lastSuccessfulRequestAt: "2026-07-27T04:00:00.000Z",
      accessToken: "must-not-be-returned",
    };
  }
}

describe("QuickBooksProductionVerificationService", () => {
  it("returns secret-free counts and report availability", async () => {
    const client = new FakeVerificationClient();
    const service = new QuickBooksProductionVerificationService(
      client,
      () => new Date("2026-07-27T05:00:00.000Z"),
    );

    const result = await service.verify({
      credentialReference: "secret://qbo",
      resources: ["company", "invoice"],
      reports: ["profit-and-loss", "balance-sheet"],
    });

    expect(result.status).toBe("healthy");
    expect(result.companyName).toBe("MOR LOGISTICS MANITOBA LIMITED");
    expect(result.recordCounts).toEqual({ company: 1, invoice: 2 });
    expect(result.reportAvailability).toEqual({
      "profit-and-loss": true,
      "balance-sheet": true,
    });
    expect(result.secretsExposed).toBe(false);
    expect(JSON.stringify(result)).not.toContain("must-not-be-returned");
    expect(client.disconnected).toBe(true);
  });

  it("marks partial verification failures unhealthy without exposing payloads", async () => {
    const client = new FakeVerificationClient();
    client.failReport = "aged-payables";
    const service = new QuickBooksProductionVerificationService(client);

    const result = await service.verify({
      credentialReference: "secret://qbo",
      resources: ["account"],
      reports: ["aged-payables"],
    });

    expect(result.status).toBe("unhealthy");
    expect(result.reportAvailability["aged-payables"]).toBe(false);
    expect(result.failures).toEqual([
      { operation: "report:aged-payables", message: "report unavailable" },
    ]);
  });

  it("redacts token-like values from authentication failures", async () => {
    const client = new FakeVerificationClient();
    client.failAuthentication = true;
    const service = new QuickBooksProductionVerificationService(client);

    const result = await service.verify({ credentialReference: "secret://qbo" });

    expect(result.status).toBe("unhealthy");
    expect(result.failures[0].message).toBe("access_token=[REDACTED]");
    expect(JSON.stringify(result)).not.toContain("secret-value");
    expect(client.disconnected).toBe(true);
  });
});
