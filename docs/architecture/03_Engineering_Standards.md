# Polaris Engineering Standards v1.1

## 1. Evidence before design

Inspect repository structure, current behavior, dependencies, tests, and release history before proposing architectural changes. Clearly separate verified facts, assumptions, and future proposals.

## 2. Architecture before major implementation

Every major feature must identify:

- purpose and work identifier;
- owning domain and architectural layer;
- affected contracts and dependencies;
- security, privacy, and failure boundaries;
- persistence and migration impact;
- test and release strategy;
- documentation and ADR impact.

## 3. Domain boundaries

Domain services should express reusable behavior without depending directly on HTTP frameworks or concrete storage. Storage is accessed through repository contracts where practical. Cross-domain access should use explicit contracts rather than internal implementation details.

## 4. Safe change workflow

1. Discover
2. Design
3. Approve scope
4. Create feature branch
5. Implement in reviewable increments
6. Add or update tests
7. Run verification
8. Update documentation
9. Open or update pull request
10. Resolve review and CI
11. Merge
12. Synchronize `main` and delete obsolete branches

Direct feature development on `main` is not the normal workflow.

## 5. Branch and commit conventions

Preferred branch patterns:

```text
feature/<work-id>-<brief-description>
docs/<brief-description>
fix/<brief-description>
release/<version>
```

Preferred commit pattern:

```text
<type>(<scope>): <imperative summary>
```

Common types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`, `release`, and `security`.

## 6. Definition of done

A milestone is complete only when applicable conditions are satisfied:

- approved scope implemented;
- critical success and failure paths tested;
- relevant automated suite passes;
- public contracts and limits documented;
- security and error behavior considered;
- architecture or ADR updated when required;
- pull request accurately describes the change;
- CI passes and review concerns are resolved;
- change is merged into `main`;
- obsolete branches are removed;
- local `main` is synchronized and clean.

## 7. Security and safety defaults

- Never commit secrets or live credentials.
- Use least privilege and explicit allowlists for high-impact integrations.
- Disable writes or execution by default when safe read-only operation is possible.
- Validate identifiers, paths, ownership, and bounded query limits.
- Do not execute source code inside static-analysis engines.
- Sanitize public errors while retaining useful internal diagnostics.
- Report uncertainty instead of presenting ambiguous conclusions as facts.

## 8. Contract conventions

- Prefer typed, domain-oriented contracts.
- Validate inputs and cross-reference integrity at boundaries.
- Keep transport models separate from core domain models when coupling would reduce reuse.
- Use bounded collection operations and explicit pagination where needed.
- Preserve backward compatibility or document migration requirements.

## 9. Testing conventions

Tests should cover:

- expected behavior;
- validation and malformed input;
- authorization, ownership, and write safeguards;
- boundaries and configured limits;
- deterministic ordering and repeatability;
- external failure translation;
- defensive copying or immutability where contracts require it;
- integration behavior at public boundaries.

Network and external service calls should be mocked in unit tests. Release verification should exercise the complete relevant suite.

## 10. Documentation conventions

Architecture documentation is living documentation. Update it whenever a change modifies domain ownership, public interfaces, persistence, runtime boundaries, integrations, security controls, or release gates.

Documentation must distinguish:

1. verified current state;
2. accepted decisions;
3. proposed future state;
4. known limitations and debt.

## 11. ADR threshold

Create or update an ADR when a decision:

- changes a major system boundary;
- introduces a runtime, platform, or persistence technology;
- changes security or authorization policy;
- changes ownership between domains;
- establishes a repository-wide engineering rule;
- is difficult or costly to reverse.

## 12. Decision rule

When speed conflicts with safety, correctness, traceability, or maintainability, Polaris chooses the safer and more reviewable path unless the Builder explicitly approves a documented exception.