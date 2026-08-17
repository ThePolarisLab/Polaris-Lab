# Motive Vehicle Utilization Timezone Source Certification

This gate reviews current **official Motive developer documentation and Help
Center articles** to try to resolve one specific, narrow question left open
by prior gates: for `GET /v1/vehicle_utilization`, when Motive says
`start_date`/`end_date` calendar-day boundaries use the "company
configured/default timezone," does that specifically mean the Motive Fleet
Dashboard's **Account Settings > Preferences > Time Zone** setting (observed
for this organization's account as **Central Time - Chicago**)?

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
   Both URLs returned consistent content.
2. `https://helpcenter.gomotive.com/hc/en-us/articles/17655615478429-How-to-update-the-time-zone-of-your-Fleet-Manager-account`
   -- Help Center article on the **individual Fleet Manager/Fleet Admin
   account** timezone preference. Direct fetch returned HTTP 403 (likely
   bot-blocked); content below is from search-result snippets of this
   specific page, not a full-page fetch, and should be treated as
   lower-confidence than Source 1.
3. `https://helpcenter.gomotive.com/hc/en-us/articles/11549950587805-How-to-change-Company-s-Time-Zone`
   -- Help Center article on a separately-titled **"Company's Time Zone"**
   setting. Same caveat: direct fetch returned HTTP 403; content below is
   from search-result snippets only.

## Findings (Paraphrased; Short Attributed Quotes Only)

### Source 1 -- official API timezone documentation (highest confidence)

- Default behavior: "The date and time specified in either the request
  parameters or the date or time attributes returned in the API responses
  are in UTC, unless a time zone is specified in an HTTP header."
- The `X-Metric-Units`-style `X-Time-Zone` header can override UTC for most
  endpoints, accepting North American zone abbreviations.
- **Rollup endpoints are explicitly called out as a distinct case**: "For
  these rollup endpoints, timestamps are computed and returned in the
  company's configured rollup timezone (for example in PT, MT, ET, and CT),
  and not in UTC and are not controlled by the `X-Time-Zone` header."
- **`vehicle_utilization` is explicitly named** as one of the example rollup
  endpoints this rule applies to (alongside `driver_utilization`). This is a
  new, direct confirmation -- prior gates had only Motive Support's written
  email as the source for "company configured/default timezone"; this is
  the first *official documentation* page independently corroborating that
  same behavior for this specific endpoint.
- **Critical gap**: this page does **not** say where or how "the company's
  configured rollup timezone" is set. No mention of "Account Settings,"
  "Fleet Dashboard," "Preferences," "Admin," or any other UI location or
  configuration mechanism appears anywhere on this page.

### Source 2 -- "Fleet Manager account" timezone (lower confidence; snippet only)

Search-result summary of this article's steps: *"Log in to the Motive Fleet
dashboard and click the profile icon. Click Account Settings. From the
Preferences section, click Edit. Click the dropdown for Time Zone and select
an option."* This UI path -- **Account Settings > Preferences > Time Zone**
-- matches exactly where the organization's account was observed showing
**Central Time - Chicago** (see `MOTIVE_UTILIZATION_UNIT_CONTEXT_EVIDENCE.md`
and the 2026-08-16 knowledge-base milestone log). The article's title frames
this specifically as **your** (an individual Fleet Manager/Fleet Admin
user's own) account setting.

### Source 3 -- "Company's Time Zone" (lower confidence; snippet only)

Search-result summary of a **separately-titled, separately-located**
article: *"Fleet Admins can change or set the Company's Time Zone settings
from Fleet Dashboard. The process involves: Log in to Fleet Dashboard and
click on Admin at the bottom left corner, then scroll down to default log
settings, click on the downward arrow to select correct time zone and
save."* This UI path -- **Admin > (Default Log Settings) > Time Zone** --
is **not the same UI location** as Source 2's Account Settings > Preferences
path. The article's title uses "Company's Time Zone," which reads as a
closer linguistic match to the API documentation's phrase "the company's
configured rollup timezone" (Source 1) than Source 2's per-user "Fleet
Manager account" framing does. The phrase "default log settings" also
suggests this setting's primary association may be with driver Hours-of-
Service log timestamps rather than analytics/rollup endpoints specifically
-- Motive's own documentation does not clarify the scope of what "Company's
Time Zone" actually governs beyond logs.

## Conclusion: OUTCOME B (Provider Timezone Behavior Known; Account Settings Binding Unresolved)

Official Motive documentation (Source 1) **newly and directly confirms**,
for `GET /v1/vehicle_utilization` by name, that rollup timestamps use "the
company's configured rollup timezone" rather than UTC or the `X-Time-Zone`
header -- upgrading this specific behavior from "Motive-Support-email-only"
to "independently corroborated by official documentation." This is a real,
incremental certification gain over the prior `CONFIRMED_PROVIDER_SUPPORT`
status, which this gate keeps but strengthens with a second, independent
source.

However, official documentation does **not** state which Fleet Dashboard UI
setting "the company's configured rollup timezone" refers to. Worse, the
available (lower-confidence, snippet-only) Help Center evidence suggests
there are **at least two distinctly-titled, distinctly-located** timezone
settings in the product:

- an individual **Account Settings > Preferences > Time Zone** (Source 2;
  this is the setting previously observed as **Central Time - Chicago** for
  this organization), and
- a separately-titled **"Company's Time Zone"** under **Admin > Default Log
  Settings** (Source 3), which has not been observed/screenshotted for this
  account at all.

No official source states these are the same setting, states they are
always kept in sync, or states which one (if either) the rollup API actually
reads from. This is not treated as *conflicting* evidence in the sense of
two authoritative sources making contradictory claims about the same
question -- it is a case of **insufficient specificity**: the API docs name
a concept ("company's configured rollup timezone") without binding it to a
UI location, and the Help Center appears to expose multiple, differently-
scoped candidate settings without clarifying which (if any) is the one the
API docs mean.

**Important correction to a prior working assumption**: earlier gates'
knowledge-base notes treated the observed **Account Settings > Preferences >
Time Zone = Central Time - Chicago** value as the natural candidate for "the
company's configured rollup timezone," while carefully avoiding certifying
it. This gate's research suggests that assumption may have been pointed at
the *wrong* candidate setting -- the separately-titled "Company's Time Zone"
(Admin > Default Log Settings), not yet observed for this account, reads as
a linguistically closer match to the API documentation's own phrasing. This
gate does not resolve which is correct; it flags the ambiguity so a future
gate or a direct account check does not simply assume Source 2 was right.

As a result, this gate certifies:

- `provider_rollup_timezone_behavior: CONFIRMED_PROVIDER_SUPPORT` (upgraded
  from single-source-email to independently doc-corroborated; unchanged
  classification label, strengthened basis)
- `vehicle_utilization_named_as_rollup_endpoint_in_official_docs: true` (new)
- `account_settings_binding: UNRESOLVED`
- `exact_company_rollup_timezone_value: DEFERRED` (unchanged)
- `candidate_settings_identified: 2` (Account Settings > Preferences >
  Time Zone; Admin > Default Log Settings > "Company's Time Zone") --
  neither certified as the API's actual source
- Scheduled automatic daily ingestion **remains blocked** on this
  certification, exactly as before this gate.

This does not change `app/motive/vehicle_utilization_semantics.py` or
`app/motive/vehicle_utilization_writer_contract.py`'s existing
`exact_company_rollup_timezone: "DEFERRED"` / `polaris_calendar_is_provider_
rollup_timezone: False` fields -- those remain accurate and are not
contradicted by this gate's findings. This gate is documentation-only and
makes no code change.

## What This Gate Does Not Do

- Does not add `X-Time-Zone` to the utilization request (Source 1 confirms
  it wouldn't affect rollup endpoints anyway).
- Does not claim `America/Chicago`, `America/Winnipeg`, or any other IANA
  zone as Motive's certified rollup timezone.
- Does not change `polaris_request_window_calendar_timezone` (`America/
  Winnipeg`, Polaris's own choice for constructing its own request windows,
  unrelated to what Motive uses internally).
- Does not unblock scheduled daily ingestion.
- Does not touch the `MotiveConnector` constructor bug fixed in PR #168.
- Does not make any live Motive API call, controlled-route invocation, or
  production validation.

## Provider Clarification Draft (Not Sent)

The following is prepared as a docs artifact only, in case a human operator
later chooses to send it. **It has not been sent, and this gate is not
authorized to send it.**

```
Subject: RE: 11006147 | Clarification of rollup-timezone source for /v1/vehicle_utilization

Your developer documentation confirms that rollup endpoints such as
vehicle_utilization compute start_date/end_date boundaries using "the
company's configured rollup timezone" rather than UTC or the X-Time-Zone
header. We want to confirm exactly which account setting that refers to
before enabling any scheduled use of this endpoint.

We are NOT asking Motive to inspect or change our account. Please confirm
specifically:

1. Is "the company's configured rollup timezone" the same setting as the
   Fleet Dashboard's Admin > Default Log Settings > Time Zone ("Company's
   Time Zone"), or the same as an individual Fleet Manager's own Account
   Settings > Preferences > Time Zone, or neither?

2. If our account has these two settings configured to different values,
   which one (if either) determines vehicle_utilization rollup date
   boundaries?

3. Is this the same timezone value used for driver Hours-of-Service log
   timestamps, or is it a separate, analytics-specific setting?

4. Is there a way to read this exact configured value via the API (rather
   than only the Fleet Dashboard UI) so an integration can confirm it
   programmatically?
```

No vehicle IDs, VINs, metric values, API key, or authorization data are
included. This artifact is intentionally not wired to any email-sending
code path.

## Remaining Blockers (Unchanged in Substance)

1. Exact company-configured Motive rollup timezone value remains `DEFERRED`
   -- now known to require resolving *which of at least two candidate
   account settings* is the actual source, not just "what value it holds."
2. Scheduled/automatic daily ingestion remains blocked on the above.
3. Checkpoint advancement implementation remains disabled (separate gate).
4. Controlled write route stays feature-flagged off by default, requiring
   separate authorization (separate gate).
