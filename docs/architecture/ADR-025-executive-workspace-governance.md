# ADR-025: Executive Workspace Governance and Separation

Status: Accepted
Date: 2026-07-26

## Context

Polaris now exposes both an Executive Workspace and a Builder Console. The Executive experience must remain safe for controlled Mor Logistics use while production connectors are introduced incrementally.

## Decision

1. Executive and Builder workspaces remain visibly and structurally separate.
2. Executive views operate in observer/advisory mode unless a later ADR authorizes a controlled mutation path.
3. Evidence, analysis, and recommended action must remain distinguishable in the user experience.
4. Runtime identity and API access must use centralized runtime configuration and the shared API client.
5. QuickBooks and Motive production adapters remain independently governed by #61 and #62.
6. Loading, empty, degraded, and retry behavior are workspace-level product requirements as live data sources are connected.

## Consequences

Polaris can be used as an executive synthesis layer before production write access exists. Connector work can progress without weakening the governance boundary or coupling Executive components directly to external systems.

## Verification

The final PGE-008.5 certification PR must pass frontend tests/build, backend runtime verification, and TypeScript core tests before Issue #78 is closed.