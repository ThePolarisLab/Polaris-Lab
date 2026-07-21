# PGE-007.4 — Decision Audit and Explainability Engine

## Purpose
Complete the Decision Intelligence stream with deterministic traceability and replay support.

## Capability
`DecisionAuditEngine.build(decision, evaluation, recommendation)` produces a structured audit record containing:

- selected option and recommendation status;
- confidence and human-readable rationale;
- evidence identifiers, direction, contribution, and explanations;
- alternative-option trade-offs;
- warnings and evaluation timestamps;
- a stable replay fingerprint.

## Validation
The engine rejects artifacts that do not reference the same decision or that select an unknown option.

## Determinism
Evidence traces and evaluation payloads are sorted before fingerprinting. Equivalent inputs produce the same replay fingerprint. The FNV-1a fingerprint is an identity/check mechanism and is not a cryptographic signature.

## Guardrails
- no hidden or fabricated reasoning;
- no source or decision execution;
- no automatic approval;
- evidence and alternatives remain visible;
- human review remains required whenever the recommendation engine returns `review_required` or `insufficient_evidence`.

## Tests
Coverage includes evidence traceability, alternatives, deterministic replay, and mismatched-artifact rejection.
