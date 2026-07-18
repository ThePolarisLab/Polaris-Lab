# ADR-001: Adopt Five Release Gates

- **Status:** Accepted
- **Date:** 2026-07-16
- **Decision owners:** Polaris Lab

## Context

Polaris needs a repeatable distinction between code that has been written and software that is ready to release. Prior discussions sometimes blurred planned, implemented, verified, and released states.

## Decision

Every material release will pass five gates:

1. **Implementation Complete** — scope and acceptance criteria are implemented.
2. **Verification Complete** — behaviour is tested and evidence is recorded.
3. **Repository Complete** — code, documentation, changelog, and decision records agree.
4. **Engineering Review Approved** — architecture, quality, security, debt, and release risk are reviewed.
5. **Release Approved** — required gates pass, versioning is finalized, and the release is authorized.

A failed gate blocks the release unless an explicit, documented exception is approved.

## Consequences

### Positive
- Clear release status
- Better auditability
- Reduced documentation drift
- Reusable release discipline

### Costs
- Additional review and documentation effort
- Releases may be delayed when evidence is incomplete

## Review trigger

Review this decision after three completed releases or when the process creates material friction without corresponding risk reduction.