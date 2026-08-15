# Motive Vehicle-Utilization Pagination Contract

This document certifies the provider pagination contract for
`GET /v1/vehicle_utilization` and describes the read-only pagination reader
built for future durable-writer use. It intentionally separates four things
that are easy to conflate:

1. the **official Motive pagination contract** (provider documentation);
2. the **previous bounded production observation** (a single page-1 call);
3. the **Polaris paginator design** (this PR's read-only implementation);
4. the **still-disabled write path** (unchanged by this PR).

## 1. Official Motive Pagination Contract

Per current official Motive documentation, GET endpoints — including
`/v1/vehicle_utilization` — use provider pagination with:

- `per_page` default `25`, maximum `100`
- `page_no` default `1`, one-based (the requested/current page number)
- a `pagination` object in the response with `per_page`, `page_no`, and
  `total` (total number of results)

The `v1/vehicle_utilization` endpoint accepts `vehicle_ids[]`, `start_date`,
`end_date`, `per_page`, and `page_no`. Polaris does not invent cursor
semantics, next-page tokens, or zero-based pages — none of these appear in
Motive's documented contract for this endpoint.

Polaris has chosen `100` (Motive's documented maximum) as the **canonical
writer page size** for future ingestion. This is a Polaris request decision,
not a Motive requirement.

## 2. Previous Bounded Production Observation

The completed bounded production evidence run (see
`MOTIVE_UTILIZATION_BOUNDED_EVIDENCE.md`) made exactly three page-1,
`per_page=3` calls and observed `pagination.total=1` for three selected
vehicles. That single observation is real evidence about the response shape,
but it never exercised a second page. This PR's certification instead relies
on official Motive documentation plus synthetic/mock multi-page tests — no
additional live Motive request was made.

## 3. Polaris Paginator Design

`chief-of-staff/backend/app/connectors/motive_vehicle_utilization_pagination.py`
adds:

- `request_vehicle_utilization_page(...)` — one no-retry, read-only page
  request. `page_no` and `per_page` must be exact positive integers (`bool`
  is rejected). The certified canonical `X-Metric-Units: true` header is
  always sent; `X-Time-Zone` and `X-User-Id` are never sent. Not exposed as a
  public API route.
- `parse_pagination_metadata(...)` — a strict, fail-closed parser for the
  `pagination` envelope. Missing keys, non-object payloads, non-`pagination`
  objects, string/float/bool values, out-of-range values, and a returned
  `page_no`/`per_page` that doesn't match the request all fail closed.
- `read_vehicle_utilization_pages(...)` — a reusable, READ-ONLY paginated
  reader for future writer use. It performs **no persistence, no checkpoint
  mutation, no commit, no flush, no add**. It:
  - requests page 1, then sequential pages `1, 2, 3, ...` up to the number of
    pages implied by `pagination.total` on page 1 (`ceil(total / per_page)`,
    or exactly one page when `total == 0`);
  - requires `pagination.total` to stay identical across every page
    (`pagination_total_changed` otherwise);
  - requires the cumulative parsed rollup count to equal `pagination.total`
    exactly once all expected pages are read (fails closed above or below);
  - treats a short page (fewer than `per_page` items) as fine as long as the
    running total is still below `pagination.total`; only an **empty** page
    returned before the total is reached fails closed
    (`premature_empty_page`);
  - fails closed on any returned rollup whose `per_page` bound is exceeded,
    that duplicates a vehicle already seen on this or an earlier page
    (`duplicate_vehicle_observed`), that isn't in the requested/selected
    vehicle set (`unexpected_vehicle_observed`), or whose `metric_units`
    doesn't pass `validate_vehicle_utilization_writer_metric_units` (i.e.
    isn't exactly `true`);
  - stops immediately on any provider HTTP failure and never requests the
    next page (no retry, no fallback call);
  - enforces a Polaris-owned safety guard, `MAX_VEHICLE_UTILIZATION_PAGES =
    100`, and fails closed **before** requesting page 2 if the page count
    implied by page 1's `pagination.total` would exceed it
    (`pagination_page_guard_exceeded`). This guard is not Motive provider
    semantics and may be revisited for much larger fleets.
- `motive_vehicle_utilization_pagination_contract_status()` — a sanitized,
  static contract summary exposed at
  `GET /api/v1/motive/fleet/vehicle-utilization-pagination-contract`
  (`CONNECTOR_READ`). This endpoint makes **zero** Motive provider calls and
  **zero** database writes; it only returns the contract constants and rule
  flags described above.

Every page in one paginated read uses the exact same `start_date`,
`end_date`, selected vehicle IDs, canonical metric-unit mode, and `per_page`
— only `page_no` changes. Request dates remain request context; Polaris does
not infer or populate provider reporting-period fields from them. A selected
vehicle missing from every returned page remains classified
`provider_rollup_absent`, exactly as in the existing bounded-evidence
contract — it is never treated as zero utilization, inactive, or an error,
and it does not by itself make the page sequence incomplete.

All behavior above is proven with synthetic/mock provider responses in
`tests/test_motive_vehicle_utilization_pagination.py`. No live Motive call
was made for this certification.

## 4. Still-Disabled Write Path

This PR is **not** the writer-enablement PR. Nothing here persists a
`MotiveVehicleUtilizationRecord`, creates a `/sync/vehicle-utilization`
route, advances a `MotiveSyncCheckpoint`, writes sync history, enables the
scheduler, enables broad Motive sync, adds Dashboard/Daily Brief attention,
converts units, or adds a migration.

The durable writer contract (`vehicle_utilization_writer_contract.py`) now
reflects that the pagination contract itself is certified and a read-only
paginator exists, but broad write ingestion remains blocked on:

- database uniqueness enforcement for the durable writer identity key;
- the utilization writer transaction implementation;
- checkpoint advancement implementation;
- the exact company-configured Motive rollup timezone, required before any
  scheduled daily ingestion.
