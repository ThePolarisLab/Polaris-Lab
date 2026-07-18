# Engineering Principles

## Core principle

> Be pragmatic in implementation. Be disciplined in architecture.

## Principles

### Architecture before implementation
Define boundaries, contracts, ownership, and failure modes before adding complexity.

### Evidence before claims
A feature is not complete because code exists. It is complete only after verification against explicit acceptance criteria.

### Human-readable systems
Code, APIs, decisions, and operational behaviour should remain understandable to future maintainers.

### Explicit trade-offs
Shortcuts may be accepted, but the reason, risk, owner, and review point must be recorded.

### Small, reversible changes
Prefer changes that can be reviewed, tested, and rolled back independently.

### Secure by design
Protect credentials, minimize privileges, validate inputs, and avoid exposing sensitive data.

### Documentation follows reality
Documentation must describe the implemented system, not an intended future state.

### Continuous improvement
Every release should improve capability, reliability, usability, security, maintainability, performance, or documentation.