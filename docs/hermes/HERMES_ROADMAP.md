# Hermes v0.8 Roadmap

## Program objective

Deliver a governed, provider-neutral integration and executive-intelligence foundation on Polaris Runtime without compromising provenance, organization isolation, explainability, security, or human authority.

## Current program state

The following increments are complete and merged:

- PGE-009.1 — Hermes Charter and Architecture — PR #51.
- PGE-009.2 — Connector Contract Foundation — PR #52.
- PGE-009.3 — Connector Orchestration Runtime — PR #53.
- PGE-009.4 — Microsoft Outlook Connector — PR #54.
- PGE-009.5 — Motive Fleet Connector — PR #55.
- PGE-009.6 — QuickBooks Financial Connector — PR #56.
- PGE-009.7 — Executive Read Model — PR #57.
- PGE-009.8 — Executive Projection Engine — PR #58.
- PGE-009.9 — Executive Query Engine — PR #59.
- PGE-009.10.1 — Hermes Certification Framework — PR #65.
- PGE-009.10.2 — Reference Connector Certification — PR #67.
- PGE-009.10.3 — End-to-End Integration & Traceability — PR #69.
- PGE-009.10.4 — Resilience & Security Verification — PR #71.
- PGE-009.10.5 — Athena Compatibility Certification — PR #73.

PGE-009.10.6 — Consolidated Hermes v0.8 Release Certification — is in progress. Release-candidate notes, the consolidated certification report, and the explicit human approval checklist are maintained on the certification branch. A v0.8 tag remains blocked until final CI evidence and human approval are recorded against the exact release commit.

## Delivered architecture

Hermes v0.8 now includes:

- provider-neutral connector contracts and lifecycle orchestration;
- checkpointed Outlook, Motive, and QuickBooks reference connectors;
- provenance-preserving evidence envelopes and deterministic idempotency;
- organization-isolated executive entities, projections, and queries;
- checkpoint recovery, replay suppression, secret redaction, and safe health signals;
- a governed certification manifest and dedicated certification CI;
- a public Hermes-to-Athena evidence compatibility boundary.

## PGE-009.10 — Integration and Certification

Completed increments:

- PGE-009.10.1 — Hermes Certification Framework — PR #65.
- PGE-009.10.2 — Reference Connector Certification — PR #67.
- PGE-009.10.3 — End-to-End Integration & Traceability — PR #69.
- PGE-009.10.4 — Resilience & Security Verification — PR #71.
- PGE-009.10.5 — Athena Compatibility Certification — PR #73.

Active final increment:

- PGE-009.10.6 — Consolidated Hermes v0.8 Release Certification — issue #74.

PGE-009.10.6 consolidates the certification manifest, requires the full regression and certification suites, publishes release notes and a release report, verifies documentation against the merged implementation, and requires human approval before tagging.

## Exit criteria

- all required automated tests and GitHub Actions pass;
- no unresolved critical or high-severity certification failures remain;
- source provenance remains demonstrable through executive insights;
- organization isolation fails closed;
- replay and idempotency behavior remains deterministic;
- Athena consumes Hermes only through governed public contracts;
- documentation matches the merged implementation;
- human review approves the v0.8 release baseline.

## Release-candidate records

- `docs/hermes/HERMES_V0.8_RELEASE_NOTES.md`
- `docs/hermes/HERMES_V0.8_RELEASE_CERTIFICATION_REPORT.md`
- `docs/hermes/HERMES_V0.8_HUMAN_APPROVAL_CHECKLIST.md`

## Post-certification direction

Candidate follow-up programs require a separate charter and ADR review. Candidates include production persistence, credential-vault adapters, executive briefing composition, authorized action proposals with human approval, and a Mor Logistics pilot.

## Non-negotiable quality gates

Every increment must preserve organization isolation, avoid plaintext secrets, retain source provenance, define replay behavior, expose safe health evidence, document exclusions, include automated tests, pass CI, and receive human review before merge.
