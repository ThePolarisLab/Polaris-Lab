# Polaris Architecture

This directory contains the living architecture baseline for Polaris.

## ARC-001 status

**Complete pending merge of PR #5.**

ARC-001 now reflects the verified repository state through 2026-07-20, including the legacy Chief of Staff application, Athena, Executive Memory, Atlas, Decision Intelligence, and the engineering-intelligence milestones.

## Documents

- `01_System_Overview.md` — system boundaries, capability layers, and architectural direction
- `02_Repository_Map.md` — verified domain ownership and repository areas
- `03_Engineering_Standards.md` — repository-wide engineering and completion rules
- `Technical_Debt.md` — current architectural risks and improvement backlog
- `adr/ADR-001-architecture-before-major-features.md` — accepted architecture-before-implementation rule

Additional feature and release ADRs may coexist elsewhere in the repository. They should be consolidated or indexed here over time without renumbering accepted decisions casually.

## Maintenance rule

Architecture documentation must distinguish:

1. **Verified current state** — confirmed from code, tests, configuration, or merged history.
2. **Accepted decision** — approved rule or direction.
3. **Proposed target state** — not yet implemented.
4. **Known limitation or debt** — verified gap requiring tracking.

The repository and merged history remain the source of truth. Material architecture changes must update the appropriate document or ADR in the same pull request.