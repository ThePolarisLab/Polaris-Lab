# ADR-014: Deterministic Decision Audit and Explainability

## Status
Accepted

## Context
PGE-007.1 through PGE-007.3 model, evaluate, and recommend decision options. Polaris also requires a durable explanation layer that traces evidence, alternatives, confidence, warnings, and replay identity without introducing hidden model reasoning.

## Decision
Introduce `DecisionAuditEngine`. It consumes a decision, its evaluation result, and its recommendation result and emits an immutable audit record containing evidence traceability, rejected alternatives, rationale, confidence, warnings, timestamps, and a deterministic replay fingerprint.

The fingerprint is generated from a stable canonical representation of decision artifacts. Timestamps are retained in the record but excluded from the replay payload where they do not affect the substantive decision.

## Consequences
- Every recommendation can be inspected and reproduced.
- Mismatched decision artifacts fail explicitly.
- Explanations remain based only on structured engine outputs.
- The fingerprint provides deterministic identity, not cryptographic security.
- The engine records decisions but does not execute them.
