# Changelog

All notable changes to Polaris Lab are documented here.

## [0.6.0] — 2026-07-19

### Added
- Atlas Entity Engine with typed, versioned entities and repository operations.
- Atlas Relationship Engine with explicit relationship vocabulary and confidence metadata.
- Knowledge Graph Core with endpoint validation, neighbor discovery, and graph integrity rules.
- Graph Query Engine with bounded breadth-first traversal, shortest paths, cycle protection, and relationship filters.
- Explainability Engine with deterministic narratives, structured evidence, and conservative confidence reporting.
- ADR-004 through ADR-008 documenting the Atlas architecture.
- Full TypeScript release verification covering Executive Memory and Atlas.

### Changed
- Package version advanced to `0.6.0`.
- GitHub Actions now runs the complete TypeScript test suite on pull requests and pushes to `main` and feature branches.

### Known limitations
- Atlas repositories remain in memory.
- Natural-language query parsing and Athena orchestration are not included yet.
- Production authorization, tenant isolation, observability, and large-scale graph storage remain future work.

## [0.3.0] — 2026-07-17

### Added
- Work Context API endpoint.
- Work Context service for entity resolution, evidence collection, and recommendation generation.
- Connector abstraction for evidence sources.
- Structured Work Context schemas.
- Foundation Day record and Polaris governance principles.
- Polaris vision, constitution, release-gate ADR, verification report, repository audit, and engineering review.

### Changed
- Registered the Work Context router in the FastAPI application.

### Known limitations
- Automated tests and CI enforcement are not included in this release.
- Production authentication, authorization, tenant isolation, and external connector hardening remain future work.
- v0.3.0 is a Foundation release and does not represent production certification.
