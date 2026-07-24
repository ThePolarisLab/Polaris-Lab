import {
  ConnectorDescriptor,
  ConnectorScope,
  EvidenceEnvelope,
  SynchronizationRequest,
} from "./contracts";

export class ConnectorContractError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly details: Readonly<Record<string, unknown>> = {},
  ) {
    super(message);
    this.name = "ConnectorContractError";
  }
}

const requireText = (value: string | undefined, field: string): void => {
  if (!value || value.trim().length === 0) {
    throw new ConnectorContractError("HERMES_REQUIRED_FIELD", `${field} is required`, { field });
  }
};

export const validateScope = (scope: ConnectorScope): void => {
  requireText(scope.organizationId, "scope.organizationId");
  requireText(scope.tenantId, "scope.tenantId");
};

export const validateDescriptor = (descriptor: ConnectorDescriptor): void => {
  requireText(descriptor.identity.id, "identity.id");
  requireText(descriptor.identity.provider, "identity.provider");
  requireText(descriptor.identity.displayName, "identity.displayName");
  requireText(descriptor.identity.version, "identity.version");
  validateScope(descriptor.scope);

  if (descriptor.capabilities.length === 0) {
    throw new ConnectorContractError(
      "HERMES_CAPABILITY_REQUIRED",
      "At least one connector capability is required",
    );
  }

  if (descriptor.supportedSyncModes.length === 0) {
    throw new ConnectorContractError(
      "HERMES_SYNC_MODE_REQUIRED",
      "At least one synchronization mode is required",
    );
  }
};

export const validateSynchronizationRequest = (request: SynchronizationRequest): void => {
  validateScope(request.scope);
  requireText(request.requestedAt, "requestedAt");
  requireText(request.correlationId, "correlationId");

  if (request.limit !== undefined && (!Number.isInteger(request.limit) || request.limit <= 0)) {
    throw new ConnectorContractError(
      "HERMES_INVALID_LIMIT",
      "Synchronization limit must be a positive integer",
      { limit: request.limit },
    );
  }

  if (request.checkpoint) {
    requireText(request.checkpoint.cursor, "checkpoint.cursor");
    requireText(request.checkpoint.observedAt, "checkpoint.observedAt");
    requireText(request.checkpoint.schemaVersion, "checkpoint.schemaVersion");
  }
};

export const validateEvidenceEnvelope = <TPayload>(envelope: EvidenceEnvelope<TPayload>): void => {
  requireText(envelope.organizationId, "organizationId");
  requireText(envelope.tenantId, "tenantId");
  requireText(envelope.source.connectorId, "source.connectorId");
  requireText(envelope.source.provider, "source.provider");
  requireText(envelope.source.sourceRecordId, "source.sourceRecordId");
  requireText(envelope.observedAt, "observedAt");
  requireText(envelope.ingestedAt, "ingestedAt");
  requireText(envelope.correlationId, "correlationId");
  requireText(envelope.schemaVersion, "schemaVersion");
  requireText(envelope.idempotencyKey, "idempotencyKey");

  if (envelope.payload === undefined || envelope.payload === null) {
    throw new ConnectorContractError("HERMES_PAYLOAD_REQUIRED", "payload is required");
  }
};

export const assertSameScope = (expected: ConnectorScope, actual: ConnectorScope): void => {
  if (
    expected.organizationId !== actual.organizationId ||
    expected.tenantId !== actual.tenantId
  ) {
    throw new ConnectorContractError(
      "HERMES_SCOPE_MISMATCH",
      "Connector request scope does not match connector scope",
      { expected, actual },
    );
  }
};
