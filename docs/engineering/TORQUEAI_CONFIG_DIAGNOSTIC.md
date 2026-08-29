# TorqueAI Configuration Diagnostic

The TorqueAI configuration diagnostic is a machine-authenticated, environment-only diagnostic for production deployments where an interactive shell is unavailable.

## Endpoint

`POST /api/v1/internal/torqueai/config-diagnostic`

The request must be empty and signed with the existing `POLARIS_TORQUEAI_SYNC_TRIGGER_SECRET` HMAC contract.

## Safety contract

The diagnostic:

- does not call TorqueAI;
- does not invoke the TorqueAI scheduler;
- does not acquire or mutate a durable dispatch claim;
- does not access or mutate the database;
- does not return the API token, base URL, organization slug, token length, token fingerprint, provider payload, or dispatch identities;
- returns only configuration-shape booleans plus explicit safety flags.

The returned shape reports whether the API token is configured and whether it appears to contain a `Bearer ` prefix, wrapping quotes, outer whitespace, or line breaks. It also reports whether the configured base URL is present and is a strict HTTPS origin.

## GitHub Actions probe

`.github/workflows/torqueai-config-diagnostic.yml` is manual-only (`workflow_dispatch`). It calls only the signed internal diagnostic endpoint and logs only an allowlisted sanitized response. It contains no TorqueAI provider token, provider URL, database credentials, scheduler call, provider call, cron, or retry.
