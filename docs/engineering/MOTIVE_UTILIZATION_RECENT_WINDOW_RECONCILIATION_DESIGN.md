# Motive Vehicle Utilization: Bounded Recent-Window Reconciliation Design

**This is a design / contract / test-planning document only. It implements
NO reconciliation runner, NO scheduler, NO checkpoint, NO new public route,
and makes NO live Motive call, Render change, feature-flag change, or
migration.** Every recommendation below is grounded in the current repo's
actual code and durable schema, audited fresh against
`574a7e2ad16c1bc0d70d6405839c1ca1aa770096` (main after PR #175, which
documented the successful `ACCOUNT_DEFAULT` live-staging validation), not
assumed or copied from an earlier gate's prose.

## 1. Repo Audit — Facts This Design Is Built On

All of the following were verified directly against current code, not
inferred:

- **Durable identity** (`app/models/motive.py`,
  `MotiveVehicleUtilizationRecord`): `uq_motive_vehicle_util_org_vehicle_request_window`
  on exactly `(organization_id, motive_vehicle_id, request_window_start,
  request_window_end)`. A legacy, retained-but-not-writer-identity
  constraint (`uq_motive_vehicle_util_org_period`, on `provider_vehicle_id` +
  `reporting_period_start/end`) also exists and is untouched by this design.
- **`write_vehicle_utilization_transaction`** (`app/motive/vehicle_utilization_writer.py`)
  takes exactly **one** `(request_window_start, request_window_end)` pair
  and one flat `rollups` sequence per call, owns exactly one commit, and
  rolls back the entire call on any failure. There is no existing primitive
  that accepts multiple windows in one call. This is architecturally
  decisive for Section 3 below.
- **The five reconciliation-mutable fields**, confirmed directly from
  `MUTABLE_ON_PROVIDER_RECONCILIATION` (`vehicle_utilization_writer.py`
  line ~136): `utilization_percent`, `idle_time`, `driving_time`,
  `idle_fuel`, `driving_fuel`. Exactly as expected — no discrepancy found.
  Every other persisted field (identity, request-window, `metric_units`,
  `parser_version`, `source_endpoint`, `provider_vehicle_id`) is immutable
  once a row exists; a difference there is `conflicting_existing_identity`,
  never a silent update. A defensive-only code path,
  `provider_rollup_reconciliation_conflict`, exists for a hypothetical
  future field that isn't identity but also isn't in the approved-mutable
  set; it is currently unreachable through real provider data and this
  design does not change that.
- **Two paginated readers exist, at different strictness/scope**:
  `_execute_one_page_controlled_read` (`vehicle_utilization_controlled_write.py`)
  is a narrow, **one-page-only** wrapper built specifically for the bounded
  controlled-validation route — it deliberately never fetches page 2. The
  **general certified reader**, `read_vehicle_utilization_pages`
  (`app/connectors/motive_vehicle_utilization_pagination.py`), is
  multi-page-capable (bounded by a Polaris-owned safety guard,
  `MAX_VEHICLE_UTILIZATION_PAGES = 100`), already fail-closed on total
  mismatch across pages, premature empty pages, duplicate/unexpected
  vehicles, and page-size violations. **This design recommends reusing the
  general reader, not the controlled-route's narrower wrapper** — a
  reconciliation runner is a different, broader use case than the
  single-page bounded validation route.
- **`MOTIVE_VEHICLE_UTILIZATION_CONTRACT_MAX_VEHICLES = 3`**
  (`motive_vehicle_utilization_contract.py`) is a **controlled-validation-specific
  safety cap**, not a reflection of real fleet size. The actual fleet (per
  operator-supplied Motive dashboard evidence in earlier gates, e.g. vehicle
  numbers in the `M22xx` range) is materially larger than 3. Vehicle-batch
  sizing for a reconciliation runner must not be confused with this
  constant; see Section 4.
- **All three unit request modes exist and are live-proven for one case**:
  `MotiveVehicleUtilizationUnitRequestMode` (`METRIC`/`IMPERIAL`/`ACCOUNT_DEFAULT`)
  in `vehicle_utilization_unit_policy.py`. `ACCOUNT_DEFAULT` is now
  live-staging-proven for exactly one day, one call, one returned rollup
  (`MOTIVE_UTILIZATION_CONTROLLED_WRITE_VALIDATION.md`'s 2026-08-18 update).
  It is **not** proven at any larger scale, batch size, or day count.
- **No retry policy exists anywhere in this stack.**
  `request_vehicle_utilization_page`'s own docstring calls itself a
  "no-retry, read-only" request. This is a deliberate, existing convention
  this design does not deviate from.
- **No existing "recent window" or "reread" precedent uses a multi-day
  single request.** Every existing caller that computes "how far back to
  look" (`_completed_vehicle_utilization_contract_window`,
  `_completed_vehicle_utilization_evidence_days`, both in `app/api/motive.py`)
  computes a small number of **separate, buffered-from-today** calendar
  days using `MOTIVE_VEHICLE_UTILIZATION_REQUEST_WINDOW_TIME_ZONE =
  "America/Winnipeg"` — explicitly documented as Polaris's own choice, "not
  asserted to equal Motive's company-configured rollup timezone." Both
  existing functions deliberately never touch "today" (the most recent
  completed day is always at least 1 day in the past). This design follows
  the same principle rather than inventing a new one.
- **Timezone binding remains Outcome B** (`MOTIVE_UTILIZATION_TIMEZONE_CERTIFICATION.md`):
  provider rollup-timezone *behavior* is confirmed (rollup endpoints use
  the company's configured timezone, not `X-Time-Zone`), but the exact
  Fleet Dashboard field supplying that value is still unresolved. This
  design does not change or resolve that; every "recent day" computed by a
  future runner inherits the same caveat every existing caller already
  carries.
- **Zero coupling to `MotiveSyncCheckpoint` anywhere in the utilization
  stack** — confirmed by direct search; every match is a docstring
  assertion that the module *never* touches it, not an actual import or
  call.

**No contradiction was found that blocks a safe design.** Nothing below
required stopping and reporting an architectural conflict.

## 2. Recommended Recent-Day Horizon: 7 days

Evaluated 3 / 7 / 14 days against: Motive Support's own guidance ("rollups
may occasionally be incomplete or later differ slightly... periodically
reread a recent rolling window" — no specific number given by Motive), the
goal of catching realistic late corrections without becoming a broad
backfill, and the existing writer's per-window atomic-commit architecture
(more days = more provider calls and more independent atomic units, not
more risk per unit — see Section 8).

- **3 days** mirrors the existing bounded-evidence precedent's buffer
  style (`day_a = today-3`, `day_b = today-2`) but was designed for a
  one-off *evidence* probe, not an ongoing correction window. Too narrow to
  give confidence that "later differ slightly" corrections, whose actual
  latency Motive never specified, are reliably caught.
- **7 days (recommended)**: no data currently proves Motive's correction
  latency, but a trailing 7-day (one calendar week) window is a
  well-established, conservative default for exactly this class of problem
  (late-arriving/eventually-consistent provider data) in comparable
  systems, and it stays firmly inside "recent correction," not "backfill."
  At the call-budget worked example in Section 12, 7 days costs only 7
  provider calls per batch per full run at current fleet size — a small,
  easily-bounded number, not a scaling risk.
- **14 days** doubles the call budget and the number of independent atomic
  units per run with no evidence-based justification — Motive gave no
  guidance suggesting corrections take that long to settle, and doubling
  the window without evidence edges toward "broad backfill," which this
  gate is explicitly not authorized to design.

**Recommendation: 7 trailing days, ending at the same "yesterday" cutoff the
existing `_completed_vehicle_utilization_contract_window` already uses** —
i.e. `[company_yesterday - 6 .. company_yesterday]` in
`America/Winnipeg` (Polaris's own non-certified choice, unchanged from
every existing caller). "Today" is never included, for the same reason it
is never included anywhere else in this codebase: it is still accumulating
and not a "completed" day. The horizon must remain a configurable parameter
in any future implementation; 7 is the recommended conservative default,
not a hardcoded constant.

## 3. Window Shape: One Calendar Day Per Window (Decision B), Not One Multi-Day Window (Decision A)

**Decision: B — one `(start_date, end_date)` request per calendar day,
`start_date == end_date`, exactly matching the existing controlled route's
own window shape (`2026-08-13..2026-08-13`).**

This is forced by the durable identity, not a stylistic preference. Durable
identity is `(organization_id, motive_vehicle_id, request_window_start,
request_window_end)`. If a reconciliation run instead requested one
multi-day window per invocation (e.g. "last 7 days" as a single
`start_date..end_date` range), two problems follow directly from that
identity:

1. **The identity would never repeat across separate runs.** A "last 7
   days" window computed today and the same "last 7 days" window computed
   tomorrow have different `(start_date, end_date)` pairs (the range slides
   forward every day). The whole point of reconciliation — revisiting and
   correcting a *specific* previously-persisted row — is structurally
   impossible if the row's own identity changes every time the window is
   recomputed. Every run would insert new rows instead of reconciling old
   ones, silently defeating the gate's purpose while still passing every
   existing writer validation (since each "new" identity really would be
   new).
2. It would also conflict with Motive's own confirmed semantics (from the
   prior unit-context-evidence gate): "each vehicle_idle_rollup is one
   aggregate for one vehicle **across the requested date range**." A 7-day
   window returns one *aggregated* rollup for the whole week, not seven
   independently-correctable daily figures — even if the identity problem
   above did not exist, a multi-day aggregate could not be reconciled
   against the day-level rows the writer already persists.

Per-day windows avoid both problems: `request_window_start ==
request_window_end == that specific day` is exactly the same value on every
future run that includes that day, so the existing writer's identical
replay / in-place reconciliation / conflict-fails-closed logic (already
fully implemented and tested) applies unmodified. **No new identity scheme,
no writer change, and no migration is required** — this is the core reason
this whole design gate can recommend "reuse existing mutable-field
reconciliation as-is" instead of designing a new one.

## 4. Vehicle Batching

**Recommendation: batch by provider page size, not by the controlled
route's `MAX_VEHICLES = 3` constant (which is unrelated — see Section 1).**
For each day-window: request up to `per_page` (100, the certified maximum)
vehicle IDs per provider call via `vehicle_ids[]=...` repeated params,
exactly as the existing pagination primitives already build the request.

- **Batch size**: up to 100 vehicle IDs per batch (the provider's own
  documented maximum `per_page`). With the real fleet materially smaller
  than 100 (per operator-supplied evidence), this means the entire fleet
  fits in **one batch** today. The design still specifies batching (rather
  than assuming "always one batch forever") so a future fleet growing past
  100 vehicles does not silently break anything — it would simply need 2+
  batches per day, handled by the existing formula in Section 12.
- **Batch independence**: each vehicle batch, for a given day, should be
  processed as its **own independent unit of work** through the existing
  writer (see Section 8 — this is what makes fine-grained failure isolation
  possible without inventing new writer machinery).
- **No inference from requested count to returned count.** Exactly as the
  existing writer and pagination reader already enforce: a vehicle
  requested-but-not-returned in a batch creates no row, no synthesized zero
  metric, and no inactive/no-activity classification — only a sanitized
  missing-count, unchanged from the controlled route's existing contract.
- **Tenant isolation is preserved by construction**: batching only changes
  how many `provider_vehicle_id`s are sent in one request; vehicle
  selection itself still comes from `MotiveVehicleRecord` rows scoped to
  the authenticated organization, exactly as every existing utilization
  code path already does. No new tenant-scoping logic is introduced or
  needed.

## 5. Pagination Policy — Reuse As-Is, No New Pagination Code

**Recommendation: reuse `read_vehicle_utilization_pages` (the general
certified reader) unmodified.** It already implements every requirement
this design would otherwise need to invent:

| Concern | Existing behavior (reused, not changed) |
| --- | --- |
| Page size | `per_page` up to 100 (`MOTIVE_VEHICLE_UTILIZATION_PAGINATION_MAX_PROVIDER_PAGE_SIZE`) |
| Max pages | Polaris-owned safety guard, `MAX_VEHICLE_UTILIZATION_PAGES = 100`, fails closed if exceeded |
| Total validation | `pagination.total` must stay identical across every page of one read; mismatch fails closed |
| Duplicate vehicle | fails closed (`duplicate_vehicle_observed`) |
| Unexpected vehicle | fails closed (`unexpected_vehicle_observed`) — the returned vehicle is outside the requested batch |
| Premature empty page | fails closed (`premature_empty_page`) before the pagination total is reached |
| Page-size violation | fails closed if a page returns more rollups than requested |

Nothing here needs loosening. **No new pagination code is recommended.**
The narrower controlled-route wrapper (`_execute_one_page_controlled_read`)
remains exactly what it is — a deliberately tighter, one-page-only
primitive for the bounded validation route — and is not reused or modified
by this design.

## 6. Unit Policy: `ACCOUNT_DEFAULT`

**Recommendation: `ACCOUNT_DEFAULT`, matching the controlled route's own,
now live-proven-for-one-case, current behavior.** No repo evidence
currently favors forcing `METRIC` or `IMPERIAL` instead. Design
requirements (all already implemented, none new):

- `X-Metric-Units` omitted entirely from every provider request.
- The returned `vehicle.metric_units` Boolean becomes the persisted unit
  context (`resolved_metric_units` in
  `VehicleUtilizationUnitPersistenceReadiness`) — never a hardcoded value,
  never a guess.
- Missing (`None`) or malformed (non-Boolean, non-`None`) returned
  indicator fails closed, exactly as today.
- No unit conversion, ever, under any mode.
- An existing row's unit context disagreeing with a reread's returned value
  is a genuine `conflicting_existing_identity` failure — the writer already
  treats a changed `metric_units` on an otherwise-matching identity as an
  immutable-context conflict, not a reconcilable field (Section 1 above),
  and this design does not change that.

**This design does not claim, and no future runner built to it may claim,
that the fleet-wide or account-wide outcome is metric or imperial.** The
2026-08-18 live validation observed exactly one rollup's outcome; nothing
broader is proven by it, and nothing broader is proven by this design
document either.

## 7. Reconciliation Semantics (Reused, Not Redesigned)

Every case below is the writer's **existing, already-implemented and
already-tested** behavior (see
`MOTIVE_UTILIZATION_HISTORICAL_RECONCILIATION.md`), confirmed directly
against current code in Section 1. This design's job is to size and bound
*how a future runner calls the writer repeatedly across days/batches*, not
to redesign what the writer does with each call.

| Case | Behavior |
| --- | --- |
| New row (no existing durable identity) | Insert. |
| Identical replay (context-compatible, all 5 mutable fields match) | True no-op — `records_unchanged` increments, no write, no timestamp touch. |
| Changed mutable value(s) (context-compatible, one or more of the 5 approved fields differ) | Reconciled in place via explicit field-by-field `setattr` (never a blind ORM merge) — `records_updated` increments, `reconciled_fields_count` sums exactly how many fields changed. |
| Changed immutable context (identity/provenance/unit-context disagrees) | Fails closed — `conflicting_existing_identity`, existing row **never** touched, whole batch rolls back. |
| Missing provider rollup (requested vehicle not returned for that day/batch) | **No row created, no zero metrics, no inactive/no-activity classification** — only the sanitized missing count. Never deleted, never zeroed, never synthesized, never inferred as "no activity." |
| Duplicate provider rollup (same vehicle twice in one batch/day response) | Fails closed before any write (`duplicate_returned_rollup`/`duplicate_vehicle_observed`, depending on which layer catches it). |
| Unexpected vehicle (returned vehicle outside the requested batch) | Fails closed (`unexpected_returned_vehicle`/`unexpected_vehicle_observed`). |
| Unit-context mismatch/conflict | Fails closed — `provider_unit_policy_mismatch` (forced modes) or the account-default missing/malformed codes; never converted, never guessed. |

## 8. Transaction Boundaries: One Transaction Per Vehicle Batch Per Day-Window (Decision C)

Evaluated:

- **A. One transaction for the entire multi-day run** — rejected. If a
  later day/batch in the run fails, rolling back the single transaction
  would also discard every earlier day/batch that had already succeeded,
  directly violating the failure-isolation requirement ("successful earlier
  windows stay committed," Section 9). This also produces an unboundedly
  large transaction as the horizon or fleet grows.
- **B. One transaction per day/window** — safe, and correctly isolates
  failures at day granularity. At today's fleet size (one batch per day),
  this is operationally identical to option C.
- **C. One transaction per vehicle batch per day-window (recommended)** —
  the finest-grained safe option, and it costs nothing extra today because
  it degrades exactly to option B whenever a day's fleet fits in a single
  batch (the current, real-world case). It future-proofs the design for
  fleet growth past 100 vehicles without requiring a later redesign: if a
  future day needs 2+ batches, a single bad batch's failure does not force
  discarding an already-committed sibling batch's rows for the same day.

**Recommendation: C, implemented by calling the existing, unmodified
`write_vehicle_utilization_transaction` once per `(day, vehicle batch)`
pair** — reusing the writer's existing atomic all-or-nothing single-commit
architecture as the natural unit of work, rather than inventing any new
transaction-spanning primitive. No writer change is required.

## 9. Failure Isolation

- **Later windows/batches continue after an earlier one fails.** Each
  `(day, batch)` unit is independent (Section 8); one unit's failure must
  not prevent attempting the remaining units in the same bounded run.
- **No automatic provider retry.** Per instruction, and because no existing
  certified retry policy exists anywhere in this stack (Section 1) to
  extend. A failed unit is recorded as failed in the sanitized run summary
  (Section 13) and left for a future, separately-authorized, manually
  re-invoked bounded run — never retried within the same run.
- **Successful earlier units stay committed.** Because each unit is its own
  transaction (Section 8), a later unit's failure cannot roll back an
  earlier unit's already-committed rows.
- **Failure is reported via the sanitized run summary only** (Section 13):
  `windows_failed`, aggregate attempted/completed counts. No raw error
  detail beyond a safe error code per the existing writer/pagination error
  taxonomy is ever included.
- **No checkpoint advances on success or failure** — see Section 10.

## 10. Checkpoint Policy — Deliberately Not a Forward-Moving Checkpoint

No checkpoint code is implemented by this gate. The future rule, however,
is a genuine design decision, not a placeholder:

- **A normal forward-moving ingestion checkpoint (`MotiveSyncCheckpoint`,
  the "process everything after position X" pattern used by
  `/sync/vehicles`/`/sync/users`) is the wrong primitive for
  reconciliation and should never be wired to it.** Reconciliation's whole
  purpose is to *repeatedly revisit* a rolling window of already-visited
  days. A forward-moving checkpoint would actively defeat that purpose —
  advancing it would cause a future run to skip re-checking days it should
  still be willing to correct.
- **Recommendation: no ingestion checkpoint at all is advanced by
  reconciliation, ever** — this is not merely deferred, it is a permanent
  architectural distinction between "ingestion progress" and
  "reconciliation lookback."
- **A separate, future, read-only "last reconciliation run" metadata
  record** (timestamp + the sanitized run summary shape from Section 13) is
  a reasonable **later** addition for observability/debugging — explicitly
  **not** a checkpoint in the ingestion sense, and explicitly **not**
  implemented by this design gate.

## 11. Idempotency / Replay

Directly inherited from the existing, already-tested writer behavior
(Section 7), applied across a full bounded run:

- Running the exact same bounded reconciliation run twice inserts nothing
  new on the second run (every day/vehicle identity already exists and is
  unchanged → `records_unchanged` for all of them).
- If none of the 5 mutable fields changed, nothing is updated.
- No row is ever duplicated — the durable unique constraint
  (`uq_motive_vehicle_util_org_vehicle_request_window`) is the final
  concurrency guard exactly as it already is for the controlled route.
- Immutable context is never altered by a replay; a genuine context
  difference fails closed instead (Section 7).
- If Motive later returns a different value for one of the 5 mutable
  fields for a day/vehicle already persisted, the **same** durable row is
  updated in place: `records_updated` increments once per affected row,
  and `reconciled_fields_count` reports exactly how many of that row's
  fields changed — summed across the whole bounded run in the sanitized
  summary.

## 12. Call-Budget Model

```
max_provider_calls = D × B × P

D = number of day-windows in the horizon (recommended: 7)
B = number of vehicle batches per day-window
    = ceil(selected_vehicle_count / per_page), per_page = 100
P = max pages per batch per day-window
    = ceil(batch_pagination_total / per_page), bounded by the existing
      Polaris safety guard MAX_VEHICLE_UTILIZATION_PAGES = 100
```

This is a deterministic **upper bound**, not an estimate — it follows
directly from the existing pagination reader's own already-certified
bounds; no new arithmetic or provider behavior is assumed.

**Worked example at the recommended horizon and current fleet size**
(fleet materially smaller than 100 vehicles, per operator-supplied
evidence): `D = 7`, `B = 1` (whole fleet fits in one 100-vehicle batch),
`P = 1` (a batch of ≤100 vehicles returns at most 100 rollups, which fits
in exactly one page of `per_page = 100`) → **`max_provider_calls = 7 × 1 ×
1 = 7`** provider calls for one complete bounded run.

**Worked example if the fleet later grows past 100 vehicles** (illustrative
only, not a claim about the current fleet): a 250-vehicle fleet at the same
7-day horizon → `B = ceil(250/100) = 3` batches, `P = 1` (each batch's
pagination total, ≤100, still fits one page) → `max_provider_calls = 7 × 3
× 1 = 21`. The formula scales predictably and remains small even at several
times today's fleet size.

## 13. Security / Privacy — Sanitized Run Summary Shape

A future reconciliation runner's result (and any log record it emits) must
follow the exact sanitization discipline already established by the
controlled route and writer — no new exception is introduced:

```
windows_attempted
windows_completed
windows_failed
vehicle_batches_attempted
provider_calls_attempted
provider_calls_completed
rollups_returned
records_inserted
records_unchanged
records_updated
reconciled_fields_count
checkpoint_advanced = false
sync_history_written = false
```

**Never included**, in any response, log record, or future admin surface,
unless a separately-authorized future gate explicitly certifies otherwise:
API key, Polaris bearer token, VINs, provider vehicle IDs (beyond
internal-only use already permitted for tenant resolution — never returned
publicly), raw provider payload, driver PII, raw request/response headers,
or raw metric values (`idle_time`, `driving_time`, `idle_fuel`,
`driving_fuel`, `utilization_percent`) in any public or admin-facing
summary. This exactly mirrors the existing controlled-write route's
response contract (`MOTIVE_UTILIZATION_CONTROLLED_WRITE_VALIDATION.md`,
"Response Shape (Sanitized Only)").

## 14. Acceptance Criteria — Decision Table

| Item | Decision | Status |
| --- | --- | --- |
| Recent-day horizon | 7 trailing days, ending at "yesterday" (never "today") | DECIDED (configurable default) |
| Window granularity | One calendar day per request/window (`start == end`) | DECIDED |
| Vehicle batch size | Up to 100 vehicle IDs per batch (provider `per_page` max) | DECIDED |
| Page size | 100 (`per_page`, already certified) | ALREADY CERTIFIED |
| Max pages | `MAX_VEHICLE_UTILIZATION_PAGES = 100` (Polaris safety guard) | ALREADY CERTIFIED |
| Unit request mode | `ACCOUNT_DEFAULT` | DECIDED (proven for 1 call only — see Section 6) |
| Transaction boundary | One transaction per vehicle batch per day-window (reuses existing writer, no new primitive) | DECIDED |
| Provider retry policy | Off — no automatic retry within a run | DECIDED |
| Omission behavior | No row, no zero metric, no inactive classification, only sanitized missing count | ALREADY CERTIFIED |
| Reconciliation mutable fields | `utilization_percent`, `idle_time`, `driving_time`, `idle_fuel`, `driving_fuel` | ALREADY CERTIFIED |
| Immutable-context conflict behavior | Fails closed (`conflicting_existing_identity`), existing row never touched | ALREADY CERTIFIED |
| Checkpoint behavior | No ingestion checkpoint ever advanced by reconciliation; a separate future "last run" record is a later, distinct, non-ingestion addition | DECIDED (implementation DEFERRED) |
| Scheduler status | Not designed, not authorized, not part of this gate | DEFERRED |
| Public route status | None recommended or designed by this gate | DEFERRED |
| Max-call formula | `D × B × P` (worked example: 7 at current fleet size) | DECIDED |

## 15. Next Gate

The next proposed engineering gate is **implementation of a bounded,
manually-invoked reconciliation runner** built on the decisions above —
still not a scheduler, still not a public route, still feature-gated and
requiring its own explicit authorization before any live call. **Scheduled
ingestion remains a later gate**, contingent on that manual runner's own
successful bounded validation and on the still-open timezone-binding
question (`MOTIVE_UTILIZATION_TIMEZONE_CERTIFICATION.md`) being resolved
first.
