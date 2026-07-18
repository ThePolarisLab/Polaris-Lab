# Changelog

All notable changes to Polaris Lab are documented here.

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