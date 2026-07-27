import {
  IntuitQuickBooksApiClient,
  QuickBooksCredential,
  QuickBooksCredentialResolver,
  QuickBooksProductionError,
} from "../../src/hermes/connectors/quickbooks";

const credential: QuickBooksCredential = {
  clientId: "client-id",
  clientSecret: "client-secret",
  refreshToken: "refresh-token",
  realmId: "realm-123",
};

class Resolver implements QuickBooksCredentialResolver {
  public references: string[] = [];
  public async resolve(reference: string): Promise<QuickBooksCredential> {
    this.references.push(reference);
    return credential;
  }
}

function jsonResponse(body: unknown, status = 200, headers?: HeadersInit): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...(headers ?? {}) },
  });
}

function companyResponse(name = "MOR LOGISTICS MANITOBA LIMITED"): Response {
  return jsonResponse({ CompanyInfo: { Id: "realm-123", CompanyName: name } });
}

function tokenResponse(token = "access-token"): Response {
  return jsonResponse({ access_token: token, refresh_token: "rotated-refresh-token", expires_in: 3600 });
}

describe("IntuitQuickBooksApiClient", () => {
  it("resolves credentials, refreshes OAuth, and verifies the exact company identity", async () => {
    const resolver = new Resolver();
    const fetchMock = jest.fn<ReturnType<typeof fetch>, Parameters<typeof fetch>>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(companyResponse());
    const client = new IntuitQuickBooksApiClient({
      credentialResolver: resolver,
      expectedCompanyName: "MOR LOGISTICS MANITOBA LIMITED",
      fetchImplementation: fetchMock,
      now: () => Date.parse("2026-07-26T12:00:00.000Z"),
    });

    await client.authenticate("secret://qbo/production");

    expect(resolver.references).toEqual(["secret://qbo/production"]);
    expect(fetchMock.mock.calls[0][0]).toBe("https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer");
    expect(String(fetchMock.mock.calls[1][0])).toContain("/v3/company/realm-123/companyinfo/realm-123");
    expect(client.getVerificationStatus()).toEqual({
      authenticated: true,
      companyName: "MOR LOGISTICS MANITOBA LIMITED",
      lastSuccessfulRequestAt: "2026-07-26T12:00:00.000Z",
      secretsExposed: false,
    });
  });

  it("rejects data when the connected company does not match Mor Logistics", async () => {
    const fetchMock = jest.fn<ReturnType<typeof fetch>, Parameters<typeof fetch>>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(companyResponse("OTHER COMPANY"));
    const client = new IntuitQuickBooksApiClient({
      credentialResolver: new Resolver(),
      expectedCompanyName: "MOR LOGISTICS MANITOBA LIMITED",
      fetchImplementation: fetchMock,
    });

    await expect(client.authenticate("secret://qbo/production")).rejects.toMatchObject({
      code: "QBO_COMPANY_MISMATCH",
    });
    expect(client.getVerificationStatus().authenticated).toBe(false);
  });

  it("builds incremental paginated queries and maps Intuit records", async () => {
    const fetchMock = jest.fn<ReturnType<typeof fetch>, Parameters<typeof fetch>>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(companyResponse())
      .mockResolvedValueOnce(jsonResponse({
        time: "2026-07-26T12:05:00.000Z",
        QueryResponse: {
          Invoice: [
            { Id: "1001", DocNumber: "INV-1001", MetaData: { LastUpdatedTime: "2026-07-25T10:00:00.000Z" } },
            { Id: "1002", DocNumber: "INV-1002", MetaData: { LastUpdatedTime: "2026-07-25T11:00:00.000Z" } },
          ],
        },
      }));
    const client = new IntuitQuickBooksApiClient({
      credentialResolver: new Resolver(),
      expectedCompanyName: "MOR LOGISTICS MANITOBA LIMITED",
      fetchImplementation: fetchMock,
      now: () => Date.parse("2026-07-26T12:05:00.000Z"),
    });
    await client.authenticate("secret://qbo/production");

    const page = await client.list("invoice", "2026-07-25T00:00:00.000Z", "1", 2);

    expect(page.records).toHaveLength(2);
    expect(page.records[0]).toMatchObject({ id: "1001", updatedAt: "2026-07-25T10:00:00.000Z" });
    expect(page.nextCursor).toBe("3");
    const queryUrl = decodeURIComponent(String(fetchMock.mock.calls[2][0]));
    expect(queryUrl).toContain("SELECT * FROM Invoice WHERE MetaData.LastUpdatedTime > '2026-07-25T00:00:00.000Z'");
    expect(queryUrl).toContain("STARTPOSITION 1 MAXRESULTS 2");
  });

  it("retries rate limits using Retry-After without exposing tokens", async () => {
    const delays: number[] = [];
    const fetchMock = jest.fn<ReturnType<typeof fetch>, Parameters<typeof fetch>>()
      .mockResolvedValueOnce(tokenResponse("secret-access-token"))
      .mockResolvedValueOnce(companyResponse())
      .mockResolvedValueOnce(jsonResponse({ fault: true }, 429, { "retry-after": "2" }))
      .mockResolvedValueOnce(jsonResponse({ QueryResponse: { Customer: [] } }));
    const client = new IntuitQuickBooksApiClient({
      credentialResolver: new Resolver(),
      expectedCompanyName: "MOR LOGISTICS MANITOBA LIMITED",
      fetchImplementation: fetchMock,
      sleep: async (delay) => { delays.push(delay); },
    });
    await client.authenticate("secret://qbo/production");

    const page = await client.list("customer");

    expect(page.records).toEqual([]);
    expect(delays).toEqual([2000]);
    expect(JSON.stringify(client.getVerificationStatus())).not.toContain("secret-access-token");
    expect(JSON.stringify(client.getVerificationStatus())).not.toContain("refresh-token");
  });

  it("refreshes and retries once after an unauthorized API response", async () => {
    const fetchMock = jest.fn<ReturnType<typeof fetch>, Parameters<typeof fetch>>()
      .mockResolvedValueOnce(tokenResponse("token-1"))
      .mockResolvedValueOnce(companyResponse())
      .mockResolvedValueOnce(jsonResponse({ fault: true }, 401))
      .mockResolvedValueOnce(tokenResponse("token-2"))
      .mockResolvedValueOnce(jsonResponse({ QueryResponse: { Account: [] } }));
    const client = new IntuitQuickBooksApiClient({
      credentialResolver: new Resolver(),
      expectedCompanyName: "MOR LOGISTICS MANITOBA LIMITED",
      fetchImplementation: fetchMock,
    });
    await client.authenticate("secret://qbo/production");

    await expect(client.list("account")).resolves.toMatchObject({ records: [] });
    expect(fetchMock).toHaveBeenCalledTimes(5);
  });

  it("returns a structured error when a credential reference is absent", async () => {
    const client = new IntuitQuickBooksApiClient({
      credentialResolver: new Resolver(),
      expectedCompanyName: "MOR LOGISTICS MANITOBA LIMITED",
      fetchImplementation: jest.fn(),
    });

    await expect(client.authenticate()).rejects.toEqual(expect.any(QuickBooksProductionError));
    await expect(client.authenticate()).rejects.toMatchObject({ code: "QBO_CREDENTIAL_REFERENCE_REQUIRED" });
  });

  it("clears all in-memory authentication state on disconnect", async () => {
    const fetchMock = jest.fn<ReturnType<typeof fetch>, Parameters<typeof fetch>>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(companyResponse());
    const client = new IntuitQuickBooksApiClient({
      credentialResolver: new Resolver(),
      expectedCompanyName: "MOR LOGISTICS MANITOBA LIMITED",
      fetchImplementation: fetchMock,
    });
    await client.authenticate("secret://qbo/production");

    await client.disconnect();

    expect(client.getVerificationStatus()).toEqual({
      authenticated: false,
      companyName: undefined,
      lastSuccessfulRequestAt: undefined,
      secretsExposed: false,
    });
    await expect(client.list("invoice")).rejects.toMatchObject({ code: "QBO_NOT_AUTHENTICATED" });
  });
});
