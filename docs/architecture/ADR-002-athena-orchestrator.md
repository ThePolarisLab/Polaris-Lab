# ADR-002: Athena Orchestrator as the single reasoning entry point

- Status: Accepted
- Date: 2026-07-18
- Release: v0.4.0 Athena Core

## Context

Polaris needs a stable way to coordinate intent classification, planning, context retrieval, decision formation, response generation, memory, and telemetry. Allowing callers to invoke these capabilities independently would duplicate workflow logic and make decisions difficult to reproduce or inspect.

## Decision

All executive reasoning requests will enter through `AthenaOrchestrator.execute`.

The orchestrator depends on explicit ports for:

- intent classification;
- execution planning;
- context assembly;
- decision formation;
- response construction;
- memory persistence; and
- telemetry.

The orchestrator owns workflow order and lifecycle state, while domain intelligence remains behind replaceable interfaces. Requests, plans, decisions, responses, and telemetry use stable typed contracts.

Athena validates a request before execution, creates a plan before gathering context, produces a structured decision before building an answer, and persists the outcome after a successful response.

## Consequences

### Positive

- One traceable reasoning path for every request.
- Infrastructure and AI providers can be replaced without changing orchestration.
- Tests can use deterministic in-memory adapters.
- Telemetry and failure handling are applied consistently.
- Future Executive Memory and Knowledge Graph work can implement existing ports.

### Trade-offs

- The orchestration layer adds structure before advanced intelligence is available.
- Long-running tool execution will eventually require cancellation and timeout policies.
- The baseline adapters are scaffolding and must not be represented as production intelligence.

## Verification

The initial unit tests verify that Athena classifies, plans, assembles context, creates a decision, builds a response, persists the decision, and records completion telemetry. They also verify rejection of invalid blank requests.
