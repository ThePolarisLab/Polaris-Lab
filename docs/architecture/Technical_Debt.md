# Polaris Technical Debt Register

This register records observed improvement opportunities without implying that they must all be fixed immediately.

## TD-001 — Hard-coded frontend API base URL

**Area:** Frontend configuration  
**Priority:** Medium  
**Observation:** `ExecutiveDashboard.jsx` uses `http://127.0.0.1:8000` directly.  
**Impact:** Deployment outside local development requires source changes.  
**Recommendation:** Move the API base URL to Vite environment configuration and centralize API access.

## TD-002 — API access embedded in a large presentation component

**Area:** Frontend architecture  
**Priority:** Medium  
**Observation:** Dashboard rendering, form state, validation, network requests, and error handling are combined in one large component.  
**Impact:** Reduced reuse and increased change risk as the UI grows.  
**Recommendation:** Introduce a small API client and progressively extract focused components/hooks.

## TD-003 — Database tables created during application import/startup

**Area:** Persistence  
**Priority:** Medium  
**Observation:** `Base.metadata.create_all(bind=engine)` is executed by the application entry point.  
**Impact:** Schema evolution is not explicitly versioned.  
**Recommendation:** Introduce database migrations before production deployment or complex schema evolution.

## TD-004 — SQLite configuration is embedded in source

**Area:** Configuration  
**Priority:** Medium  
**Observation:** The database URL is hard-coded as `sqlite:///./polaris.db`.  
**Impact:** Environment-specific database configuration is difficult.  
**Recommendation:** Read the database URL from environment configuration with a safe local default.

## TD-005 — Repeated database dependency patterns

**Area:** Backend API  
**Priority:** Low  
**Observation:** Routers may define local `get_db` dependencies.  
**Impact:** Duplication and possible inconsistency.  
**Recommendation:** Verify all routers and centralize the shared database dependency where duplication exists.

## TD-006 — GitHub client request method lacks pagination abstraction

**Area:** GitHub Engine  
**Priority:** High for PGE-002  
**Observation:** Current branch listing requests a single page with `per_page=100`; the generic client does not yet provide pagination handling.  
**Impact:** Repository Intelligence could silently return incomplete trees, commits, branches, or search results.  
**Recommendation:** Add bounded pagination helpers before implementing collection-heavy PGE-002 operations.

## TD-007 — GitHub API errors may expose raw response details

**Area:** Security and integration errors  
**Priority:** Medium  
**Observation:** The client includes the raw GitHub error body in `GitHubEngineError`.  
**Impact:** Internal or sensitive integration details may be returned through API error responses.  
**Recommendation:** Log detailed errors internally and return sanitized public messages with stable error codes.

## TD-008 — GitHub path encoding requires review

**Area:** GitHub Engine correctness  
**Priority:** High for PGE-002  
**Observation:** Repository paths are interpolated directly into contents API paths after basic parent-directory validation.  
**Impact:** Spaces, reserved characters, Unicode, and unusual branch/path names may fail or behave unexpectedly.  
**Recommendation:** Add explicit URL encoding and tests for valid edge-case paths.

## TD-009 — Incomplete architecture and API inventory

**Area:** Documentation  
**Priority:** High during ARC-001  
**Observation:** The first baseline confirms major modules but does not yet enumerate every endpoint, schema, model field, relationship, or test.  
**Impact:** Change-impact analysis remains incomplete.  
**Recommendation:** Continue evidence gathering before finalizing PGE-002 design.

## TD-010 — Dependency versions use `latest`

**Area:** Frontend build reproducibility  
**Priority:** Medium  
**Observation:** Frontend dependencies are declared using `latest`.  
**Impact:** Fresh installs may receive breaking versions and produce non-reproducible builds.  
**Recommendation:** Pin compatible versions and maintain the lock file.

## Review policy

Each item should eventually receive an owner, target milestone, and status (`open`, `accepted`, `in progress`, `resolved`, or `deferred`). Priorities should be reassessed when the affected area is being changed.
