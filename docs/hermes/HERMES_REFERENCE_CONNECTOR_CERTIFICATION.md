# Hermes Reference Connector Certification

## Scope

This report records automated certification of the Microsoft Outlook, Motive, and QuickBooks Online **reference connector implementations** delivered in PGE-009.4 through PGE-009.6.

It certifies deterministic behaviour at the Polaris provider boundary using controlled clients. It does not certify live provider availability, real production credentials, vendor service-level agreements, or the correctness of external provider data.

## Certified implementations

- Microsoft Outlook reference connector;
- Motive reference connector;
- QuickBooks Online reference connector.

## Passed criteria

| Criterion | Evidence | Result |
| --- | --- | --- |
| Provider-neutral descriptor conformance | `tests/certification/referenceConnectorCertification.test.ts` | Passed |
| Declared read, full-sync, incremental-sync, and health capabilities | automated descriptor assertions | Passed |
| Organization and tenant isolation fails closed | cross-scope negative tests | Passed |
| Source observations produce governed evidence envelopes | envelope invariant assertions | Passed |
| Provider, connector, scope, schema, source-record, and correlation metadata are retained | provenance assertions | Passed |
| Credential references are absent from serialized evidence | negative secret-leak assertions | Passed |
| Replay preserves deterministic idempotency keys | repeated-source replay tests | Passed |
| Connector checkpoints declare provider-specific schema versions | checkpoint assertions | Passed |
| Connected connectors report healthy state | health contract assertions | Passed |
| Disconnect transitions connectors to the disconnected state | lifecycle assertions | Passed |

## Deferred criteria

The following are intentionally deferred to later PGE-009.10 increments:

- live-provider authentication and availability;
- production credential-vault integration;
- rate-limit and provider-outage exercises;
- durable runtime restart and checkpoint recovery under injected failure;
- connector-to-projection-to-query traceability;
- performance benchmarks against production-sized datasets;
- Mission Control operational dashboards;
- consolidated security review.

## Exclusions

- autonomous Outlook email sending;
- autonomous QuickBooks entries or payments;
- any write capability not explicitly governed and approved;
- vendor certification or endorsement by Microsoft, Motive, or Intuit.

## Certification decision

The three reference connectors are approved as conforming implementations of the Hermes provider-neutral read and synchronization contracts, subject to the deferred production and end-to-end criteria above.

This decision becomes effective only after automated CI passes and the pull request receives human review and is merged.
