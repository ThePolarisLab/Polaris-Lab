# Hermes Resilience & Security Certification

## Milestone

PGE-009.10.4 verifies that Hermes can resume interrupted processing, suppress duplicate work, isolate connector and organization checkpoints, redact credentials, and publish operational health without exposing secrets.

## Certified properties

### Checkpoint recovery

`ResilientCheckpointRunner` persists progress only after a record is handled successfully. A failed record is therefore retried after restart, while previously completed records are not repeated.

### Replay determinism

Each stream checkpoint records processed idempotency keys. Replayed records with an already processed key are skipped and the cursor advances deterministically.

### Failure isolation

Checkpoint identity includes the connector stream and organization boundary. Failure or progress in one connector or organization cannot advance another stream.

### Secret boundary

`redactSensitive` recursively redacts credential-shaped fields and bearer tokens before telemetry or health state leaves the resilience boundary. The certification suite includes negative assertions proving representative secrets are absent from serialized output.

### Safe operational health

`safeConnectorHealth` preserves connector identity, organization identity, status, timestamp, and useful failure context while sanitizing the message payload.

## Automated evidence

- `tests/certification/resilienceSecurityCertification.test.ts`
- `src/hermes/resilience.ts`
- `tests/certification/certificationManifest.ts`

## Certification result

- HCF-007 — passed
- HCF-008 — passed
- HCF-010 — passed

## Explicit exclusions

This increment provides provider-neutral in-memory certification primitives. Production database checkpoint adapters, external secret-vault integrations, distributed leases, and alert delivery are intentionally deferred to deployment-specific increments.
