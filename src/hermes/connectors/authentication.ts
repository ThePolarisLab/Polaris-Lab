import { ConnectorContext, ConnectorId, ConnectorScope, CredentialReference } from "./contracts";

export enum AuthenticationScheme {
  OAuth2 = "oauth2",
  ApiKey = "api-key",
  ClientCredentials = "client-credentials",
  ServiceAccount = "service-account",
}

export interface AuthenticationRequirement {
  readonly scheme: AuthenticationScheme;
  readonly credentialReference: CredentialReference;
  readonly scopes: readonly string[];
}

export interface AuthenticationResult {
  readonly connectorId: ConnectorId;
  readonly scope: ConnectorScope;
  readonly authenticated: boolean;
  readonly authenticatedAt: string;
  readonly expiresAt?: string;
  readonly grantedScopes: readonly string[];
  readonly failureCode?: string;
  readonly failureMessage?: string;
}

export interface IAuthenticationProvider {
  readonly scheme: AuthenticationScheme;

  authenticate(
    connectorId: ConnectorId,
    requirement: AuthenticationRequirement,
    context: ConnectorContext,
  ): Promise<AuthenticationResult>;

  revoke?(
    connectorId: ConnectorId,
    requirement: AuthenticationRequirement,
    context: ConnectorContext,
  ): Promise<void>;
}
