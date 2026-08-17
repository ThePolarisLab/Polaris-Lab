# Motive Vehicle Utilization Timezone Source Certification

This gate reviews current **official Motive developer documentation and Help
Center articles** to try to resolve one specific, narrow question left open
by prior gates: for `GET /v1/vehicle_utilization`, when Motive says
`start_date`/`end_date` calendar-day boundaries use the "company
configured/default timezone," which Motive account setting supplies that
value?

It makes **no** live Motive API call. It does **not** run controlled
production validation. It does **not** modify utilization reconciliation or
unit semantics, does not touch the `MotiveConnector` constructor (PR #168,
already merged, out of scope), does not enable scheduling, does not advance
checkpoints, does not rotate the API key, and does not merge.

## Sources Reviewed

Retrieved **2026-08-17** from `developer-docs.gomotive.com` and
`helpcenter.gomotive.com` (Motive's official primary-source developer
documentation and support Help Center):

1. `https://developer-docs.gomotive.com/docs/time-zone` and its
   `https://developer-docs.gomotive.com/reference/time-zone` counterpart --
   Motive's dedicated official documentation page for API timezone behavior.
2. `https://helpcenter.gomotive.com/hc/en-us/articles/17655615478429-How-to-update-the-time-zone-of-your-Fleet-Manager-account`
   -- Help Center article on the individual Fleet Manager/Fleet Admin account
   timezone preference. Direct fetch returned HTTP 403; only search-result
   snippets were available.
3. `https://helpcenter.gomotive.com/hc/en-us/articles/11549950587805-How-to-change-Company-s-Time-Zone`
   -- Help Center article on a separately titled company timezone setting.
   Direct fetch returned HTTP 403; only search-result snippets were available.
4. Direct Fleet Dashboard observations supplied by the operator on
   **2026-08-17**:
   - **Account Settings > Preferences > Time Zone** =
     `(GMT-05:00) Central Time - Chicago`
   - **Admin > Compliance > General > Home terminal time zone** =
     `(GMT-05:00) Central Time - Chicago`

The direct UI observations are account-specific evidence, not provider
documentation of the API binding itself.

## Findings

### Official API timezone documentation

Motive's official timezone documentation directly identifies
`vehicle_utilization` as a rollup endpoint. The documentation states that
rollup endpoints use the **company's configured rollup timezone** and are not
controlled by `X-Time-Zone`.

The remaining gap is that this page does **not** say which Fleet Dashboard
field supplies that configured rollup timezone.

### Fleet Manager account timezone

The per-user **Account Settings > Preferences > Time Zone** setting was
directly observed for this organization as **Central Time - Chicago**.

### Company/compliance timezone

The company-level setting was directly observed in the current Fleet Dashboard
at **Admin > Compliance > General > Home terminal time zone**, also set to
**Central Time - Chicago**.

This company-level Compliance value is the stronger operational candidate for
the API documentation's phrase "the company's configured rollup timezone"
than the per-user Account Settings preference. However, no official Motive API
source reviewed in this gate explicitly states that `/v1/vehicle_utilization`
reads this exact field.

### Account-specific convergence

Both plausible UI candidates currently resolve to the same displayed zone:

- Account Settings > Preferences: **Central Time - Chicago**
- Admin > Compliance > Home terminal time zone: **Central Time - Chicago**

Therefore there is **no observed operational mismatch between the two
candidate settings on this account today**. This materially reduces near-term
risk for a single bounded controlled validation, even though the exact API-to-
UI binding remains unconfirmed.

## Conclusion: OUTCOME B (Provider Timezone Behavior Known; Exact UI Binding Unresolved)

Official Motive documentation directly confirms, for
`GET /v1/vehicle_utilization`, that rollup timestamps use the company's
configured rollup timezone rather than UTC or the `X-Time-Zone` header.

The exact Fleet Dashboard field supplying that provider value remains
unresolved. However, direct account observation now shows that both plausible
candidates are configured to the same zone, **Central Time - Chicago**, and
the company-level **Admin > Compliance > Home terminal time zone** is adopted
as Polaris's **provisional operational timezone source** for the next bounded
controlled production validation only.

This is deliberately not upgraded to OUTCOME A. Motive Support confirmation is
still pending, and no claim is made that the Home terminal time zone is the
provider-certified API source.

As a result, this gate records:

- `provider_rollup_timezone_behavior: CONFIRMED_PROVIDER_SUPPORT`
- `vehicle_utilization_named_as_rollup_endpoint_in_official_docs: true`
- `account_settings_binding: UNRESOLVED`
- `company_compliance_timezone_observed: true`
- `company_compliance_timezone_display_value: "Central Time - Chicago"`
- `account_preference_timezone_display_value: "Central Time - Chicago"`
- `candidate_settings_currently_match: true`
- `provisional_operational_timezone_source: "Admin > Compliance > Home terminal time zone"`
- `provisional_operational_timezone_value: "Central Time - Chicago"`
- `exact_company_rollup_timezone_value: DEFERRED`
- `controlled_production_validation_allowed_under_provisional_assumption: true`
- scheduled/automatic daily ingestion remains a later gate and is not enabled
  by this document.

This does not change
`app/motive/vehicle_utilization_semantics.py` or
`app/motive/vehicle_utilization_writer_contract.py`'s existing
`exact_company_rollup_timezone: "DEFERRED"` /
`polaris_calendar_is_provider_rollup_timezone: False` fields. Those remain
accurate until Motive confirms the exact binding.

## What This Gate Does Not Do

- Does not add `X-Time-Zone` to the utilization request.
- Does not claim `America/Chicago`, `America/Winnipeg`, or any other IANA zone
  as Motive's certified rollup timezone.
- Does not change `polaris_request_window_calendar_timezone`
  (`America/Winnipeg`, Polaris's own choice for constructing request windows).
- Does not enable scheduled daily ingestion.
- Does not advance checkpoints.
- Does not touch the `MotiveConnector` constructor bug fixed in PR #168.
- Does not make any live Motive API call or controlled-route invocation.

## Provider Clarification Sent

A concise clarification was sent to Motive API Support on the existing support
thread on **2026-08-17** asking which Fleet Dashboard setting actually drives
the `/v1/vehicle_utilization` rollup timezone, including whether the company
Compliance/Home terminal timezone is the relevant source.

No vehicle IDs, VINs, metric values, API key, or authorization data were
included.

Until Motive replies, Polaris may use the observed company-level
**Central Time - Chicago** value as a provisional operational assumption for
the single bounded controlled production validation. If Motive later confirms
a different source or value, Polaris must update the assumption before any
broad scheduled ingestion.

## Remaining Blockers / Next Gates

1. Exact API-to-UI timezone binding remains `DEFERRED` pending Motive Support
   confirmation.
2. One explicitly authorized bounded controlled production validation may
   proceed using the provisional company/compliance timezone assumption.
3. Checkpoint advancement remains disabled and requires a separate gate.
4. Scheduled/automatic daily ingestion remains disabled and requires a
   separate gate after controlled validation and checkpoint safety are
   established.
