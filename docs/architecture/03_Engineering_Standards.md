# Polaris Engineering Standards v1.0

## 1. Evidence before design

Repository structure, current behavior, and dependencies must be inspected before architectural changes are proposed. Documents must clearly separate verified facts from recommendations.

## 2. Architecture before major implementation

Every major feature must identify:

- its purpose;
- architectural layer and owning domain;
- affected modules and interfaces;
- security implications;
- test strategy;
- documentation impact.

## 3. Layer responsibilities

### API layer

FastAPI routers should handle transport concerns: validation, dependency injection, status mapping, and response serialization. Business and integration logic should be delegated to services or engine clients.

### Domain/service layer

Services and engines should implement reusable application behavior without depending on HTTP request objects.

### Persistence layer

Database setup, sessions, models, and future repository abstractions should remain isolated from frontend and external-integration code.

### Integration layer

External systems such as GitHub should be accessed through dedicated clients with explicit configuration, error translation, timeouts, and security safeguards.

### Presentation layer

React components should progressively separate display components, API access, and reusable state logic as the frontend grows.

## 4. Safe change workflow

Major changes should follow:

1. Discover
2. Design
3. Builder approval
4. Feature branch
5. Small implementation commits
6. Automated tests
7. Documentation
8. Pull request
9. Review and merge

Direct feature development on `main` is not the normal workflow.

## 5. Branch and commit conventions

Preferred branch pattern:

```text
feature/<work-id>-<brief-description>
```

Examples:

```text
feature/arc-001-architecture-review
feature/pge-002-repository-intelligence
```

Preferred commit pattern:

```text
<type>(<scope>): <imperative summary>
```

Common types include `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, and `security`.

## 6. Feature completion standard

A feature is complete when it has:

- working implementation;
- automated tests covering critical behavior and failure paths;
- documentation describing purpose, configuration, and interfaces;
- a reviewable pull request.

## 7. Security defaults

- Never commit secrets or live tokens.
- Prefer environment-based configuration.
- Use least privilege.
- Disable destructive or write operations by default.
- Validate repository paths and user-controlled identifiers.
- Use explicit allowlists for high-impact integrations where practical.
- Preserve Builder approval for material engineering changes.

## 8. API conventions

- Use stable, domain-oriented prefixes.
- Use Pydantic schemas for external request and response contracts.
- Translate internal errors into intentional HTTP responses.
- Avoid exposing raw external-service payloads unless the endpoint explicitly promises them.
- Add pagination or bounded limits to collection endpoints.

## 9. Testing conventions

Critical areas should include tests for:

- expected success behavior;
- validation failures;
- permissions and disabled-write safeguards;
- external API failure translation;
- unsafe path and input rejection;
- service behavior independent from HTTP routing.

Network calls should be mocked in unit tests.

## 10. Documentation conventions

Architecture documentation is living documentation. Any change that modifies module ownership, public endpoints, persistence models, external integrations, or security boundaries must update the corresponding architecture document or ADR.

## 11. ADR threshold

Create an Architecture Decision Record when a decision:

- changes a major system boundary;
- introduces a new platform or persistence technology;
- affects security or authorization policy;
- changes ownership between engines/domains;
- is difficult or costly to reverse;
- establishes a reusable engineering rule.
