# Supplier price reconciliation preview V1

## Scope and authorization

User-approved next phase after BVD/Eco invoice certification: compare existing
supplier price evidence with supplier invoice billed prices. This slice is a
read-only, on-demand preview, not a persisted approval or accounting adjustment.
It does not call Outlook, Motive, suppliers, payments, schedulers or ingestion.
No migration, new dependency, frontend or manual rate-entry workflow is added.

GET /api/v1/fuel/invoices/{invoice_run_id}/price-reconciliation

Requires existing bearer/organization authentication and ORGANIZATION_READ.
The authenticated organization owns every invoice and quote query. A foreign
invoice ID gets the same 404 as an absent ID. Incomplete evidence or exceeded
bounds produces a sanitized 409, never a partial success result.

## Evidence gate completed

PR #275 corrected Eco USD blank MC cells and cross-page transactions.
The authorized read-only database inspection of MOR's U9165021 found run 4
completed at 2026-09-01T20:27:52.611Z, 135 distinct rows numbered 1-135,
no error, and populated Outlook message/attachment provenance.
The stored SHA-256 matched the exact source PDF inspected locally.
The subsequent user-run API request returned idempotent_replay with 135 rows.
BVD 992481 (30 rows) and Eco CAD C9193095 (4 rows) had already imported/replayed.
This closes invoice ingestion certification, not production price-comparison certification.

## Matching and arithmetic policy

- Match only completed, internally consistent source runs for the same tenant,
  supplier, currency and company. Verify source hashes, counts and effective dates.
- Use the supplier-reported transaction calendar date without guessing a timezone.
  BVD effective ranges are inclusive; Eco effective dates are single days.
- First use a quote covering the transaction date. If none qualifies, search
  backward through seven previous days, nearest first. Never use a future quote.
- Every fallback remains explicitly labelled, including a zero rate difference:
  "Exact effective-date quote unavailable; prior-date quote used."
- BVD uses supplier site ID and region when available. Do not substitute a name
  when the supplied ID fails. Eco without an ID requires exact full station-name
  and region matching (plus city if independently present on the quote).
  Case/whitespace normalization only; no fuzzy, city-only, brand or geographic aliases.
- Require matching product labels. BVD truck TA maps to explicit ULSD.
  Blank BVD CAD product labels do not become diesel by assumption. ULSR/TF
  are not automatically equated to ULSD, and DEF is not diesel.
  MC/OTHER are not applicable to this fuel price comparison.
- BVD and Eco USD compare Your Price; Eco CAD compares Total Price,
  never its pre-tax Price. Original source strings remain unchanged.
- Decimal comparison has zero tolerance: every non-zero difference is returned.
  The signed analytical impact is quantity times (billed minus quote).
  It is not a supplier-authored amount, refund, accounting entry or confirmed loss.
- Where source components exist, check retail minus savings against quote;
  Eco CAD checks Price plus GST/HST against Total Price. Contradictions stay
  unresolved; values are not swapped, recalculated into the source, or corrected.
- Multiple qualifying quotes on a date are ambiguous, even if prices agree;
  no undocumented supersession policy selects one.

## Result meaning and limits

Results are match, price_difference, fallback_match, fallback_difference,
unresolved or not_applicable. Each resolved/fallback row links invoice and quote
IDs, hashes, filenames, effective dates, comparison field, rates and policy version.
No driver names, card identifiers or OAuth material are returned.

Missing sheets mean no completed matching rate sheet is stored. The preview
cannot claim no email was received because it does not inspect the mailbox.
Location absence and product absence are separate unresolved reasons.
The result requests supporting supplier rate evidence; this PR does not implement
manual entry or upload.

Bounds: one invoice, up to 1,000 lines, 500 price runs and 20,000 quote rows.
Database reads are bounded and use no_autoflush; no evidence is changed.
Results may change when new quote evidence is imported, so this preview must not
be treated as an immutable reconciliation decision.

## Known coverage limits and next gate

Eco location strings can differ between rate lists and invoices. CAD lists may
identify only a city; there is no approved alias registry. BVD CAD omits product
labels. These legitimate gaps can leave many rows unresolved. Do not relax those
guards to manufacture coverage. Missing historical rate sheets are not imported
automatically. Future station/product mapping needs separate source-backed review.

Tests cover exact/fallback boundaries, nearest-date choice, tiny differences,
negative analytical differences, tax basis, anomalies, ambiguous evidence,
nonfuel categories, unsupported mappings, query bounds, consistency, tenant
isolation, API auth/permission and read-only execution.

After exact-head CI and human merge, certify this GET preview separately against
stored evidence. Do not enable Motive reconciliation or supplier actions.
