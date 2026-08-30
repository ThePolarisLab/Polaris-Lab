# Polaris Handoff - 2026-08-29

Status: Current handoff for continuation in a new engineering conversation
Repository: `ThePolarisLab/Polaris-Lab`
Main SHA at handoff: `8d46212ba8b13a7f97cb7dc1b8974c23b9d625db`
Latest merged PR: #252 `ci(torqueai): enable hourly dispatch sync`

## Working rules

- Human owner manually merges all PRs.
- Never auto-merge and never enable auto-merge.
- Branch from the exact latest `main`.
- Open Draft PRs first.
- GitHub Actions on the exact final head are authoritative for merge readiness.
- Do not claim a workflow ran if it did not register.
- Inspect failures before rerunning; no blind retries.
- Avoid unnecessary production-provider calls.
- Keep provider credentials and raw sensitive payloads out of source, logs and chat.
- Production external-system behavior remains read-only/advisory unless separately governed and explicitly authorized.

## Current product position

Polaris is in **late Track 4 / pre-Track 4D**.

The core transition is from independently trusted connectors toward cross-source executive intelligence:

`Connect -> Verify -> Persist -> Automate`

becomes

`Correlate -> Reason -> Prioritize -> Advise`

The intended Owner Alpha outcome is for the MOR Logistics owner to open Polaris first each morning and understand the 3-5 most important management items in approximately five minutes.

## Infrastructure / platform baseline

- Python/FastAPI backend is the authoritative operational runtime.
- React Executive Workspace exists with authenticated sign-in.
- Executive routes include Dashboard, Daily Brief, Dispatch, ACE, Evidence, Decision Center, Connectors, System Health and Builder Console.
- Owner Alpha should remain Observer / Advisory mode.
- PostgreSQL lifecycle and tenant isolation are governed through SQLAlchemy/Alembic and CI gates.
- Production/staging data persistence has been moved to external Neon PostgreSQL after Render database constraints.
- GitHub Actions is used for CI and controlled scheduler wakeups.

## Connector status

### QuickBooks Online - Track 4A

Target:
- QuickBooks remains Financial System of Record;
- Polaris synchronizes read-only financial evidence and owns executive intelligence;
- executive financial KPIs must preserve QuickBooks authoritative totals.

Reached:
- production OAuth works;
- Mor Logistics company verification succeeded;
- production read-only synchronization succeeded;
- durable financial snapshots exist;
- Revenue and Total Expenses reconciled.

Remaining:
- Accounts Receivable reconciliation;
- Accounts Payable reconciliation;
- Gross Profit validation;
- Net Income validation;
- Cash Position validation;
- financial exceptions/risks feeding the Daily Brief.

Interpretation:
- connector connectivity is effectively complete;
- remaining work is financial reconciliation and intelligence.

### Outlook - Track 4B

Target:
- secure, tenant-bound, read-only Microsoft Graph connector;
- delegated `Mail.Read` only;
- checkpointed message sync;
- evidence/provenance;
- deterministic classification;
- executive attention;
- no send/delete/move/reply mutations.

Reached:
- OAuth/token persistence architecture implemented;
- Outlook folders/messages/attachment metadata/classification/sync history implemented;
- checkpoints/delta architecture implemented;
- Connector/System Health surfaces implemented;
- Outlook access works for the production ACE daily-report pipeline.

Remaining:
- full general mailbox production confidence testing;
- classification/attention quality review;
- broad operational-email attention feeding Daily Brief;
- later cross-source correlation with loads/customers/finance.

### Motive - Track 4C

Original target:
- vehicles, drivers, locations, mileage/utilization, HOS, fuel/IFTA where supported, and fleet operational intelligence.

Reached:
- Company API Key production architecture;
- vehicle ingestion;
- company-user ingestion;
- utilization contract/pagination/unit semantics certified;
- durable utilization persistence;
- production checkpointing;
- daily automatic scheduler;
- seven-day utilization history;
- multiple dashboard KPIs/observations including utilization and fuel-burn-related measures;
- production scheduler resilience/logging hardening merged through PRs #249/#250.

Remaining from full original Track 4C scope:
- authoritative driver classification;
- vehicle-driver association;
- location operational intelligence;
- HOS management intelligence;
- broader safety/inspection/maintenance/fault intelligence;
- wider IFTA/fuel scope where useful;
- richer Motive exceptions in Daily Brief.

Direction:
- do not expand Motive just because endpoints exist;
- add new scope when a Track 4D/Owner Alpha question requires it.

### ACE / Bond Control

Target:
- make Polaris the management/control surface for MOR in-bond exposure using the approved ACE daily source;
- persist/reconcile movements;
- detect exceptions;
- track authorization and resolution;
- surface important ACE attention in Daily Brief.

Reached:
- durable ACE movements/events/import runs;
- search, filters and counters;
- Active/Open/Exceptions/Overdue/Late/Unauthorized views;
- BOL/PAPS, shipper/consignee, QP filer and carrier context;
- authorization classification;
- resolve/reopen lifecycle;
- movement history;
- Outlook XLSX importer;
- source-message idempotency;
- scheduled GitHub wakeups with redundancy;
- Daily Brief ACE management attention.

Deferred:
- standalone Manifest ingestion;
- direct CBP portal/API automation;
- automatic material external actions.

### TorqueAI - Dispatch

Target:
- official, bounded, backend-only dispatch connector;
- durable tenant-scoped storage;
- read API and Dispatch dashboard;
- safe automatic synchronization;
- later dispatch exceptions/correlation.

Reached:
- read-only external connector designed and implemented;
- Bearer authentication and safe diagnostics established;
- production connector successfully certified;
- durable dispatch ingestion implemented;
- read API implemented;
- Dispatch dashboard implemented;
- durable hourly claim/idempotency implemented;
- controlled production certification on 2026-08-29 for the 21:00 UTC slot succeeded:
  - HTTP 200;
  - status `executed`;
  - 1 page fetched;
  - 31 rows validated;
  - 23 inserted;
  - 1 updated;
  - 7 unchanged;
  - no raw dispatch payload or secrets exposed;
- PR #252 merged Stage 2 schedule `17 * * * *` while retaining manual `workflow_dispatch` and no application-level provider retry;
- first natural post-merge schedule also succeeded on exact merge SHA `8d46212ba8b13a7f97cb7dc1b8974c23b9d625db`:
  - workflow run #8 / run ID `33283222863`;
  - created 2026-08-30 00:24 UTC;
  - HTTP 200;
  - status `executed`;
  - trigger slot `2026-08-30T00:00:00Z`;
  - 31 rows validated;
  - 0 inserted;
  - 1 updated;
  - 30 unchanged;
  - tenant scope validated;
  - no raw dispatch payload or secrets exposed.

Immediate remaining check:
- observe continued hourly schedule reliability over a short period; the first natural Stage 2 execution is already proven.

Do not rerun previously consumed hourly slots.

## New strategic evidence streams

The project now treats seven evidence streams as strategically important for MOR Owner Alpha:

1. TorqueAI - loads/dispatch
2. Motive - fleet operations
3. Fuel suppliers - fuel price/quantity/transaction/invoice control
4. Outlook - external business communication
5. Internal communications - Teams preferred path under pilot; WhatsApp official API feasibility under separate test
6. ACE - customs/bond exposure
7. QuickBooks - financial truth

## Fuel direction - proposed Track 4E

Fuel is a major MOR operating cost and price volatility is material. Historical supplier invoicing problems have included both quantity and pricing discrepancies.

Fuel should be treated as a first-class control connector.

Fuel V1 target:
- supplier transaction ID;
- timestamp;
- station/location;
- gallons/litres;
- product;
- posted/base price if available;
- MOR contracted/net price if available;
- taxes/fees;
- total amount;
- truck/unit/card/driver references when available;
- invoice/reference number;
- current station price feed where supported.

Fuel V1 outcome:
> Independently compare what MOR bought with what the supplier charged and surface quantity/price discrepancies.

Later:
- route-aware fuel plans;
- actual-versus-plan monitoring;
- high-cost/unplanned fueling exceptions;
- avoidable-cost estimates;
- cross-source use of TorqueAI/Motive/internal communications.

Fuel supplier API outreach has already been considered/requested for suppliers such as BVD Petroleum and Eco Petroleum. Do not assume an API contract until each supplier provides/approves it.

## Internal communications direction - WhatsApp vs Teams

Operational reality:
- MOR currently relies heavily on WhatsApp groups for Drivers, Workshop, Back Office and Management communication;
- this is a major source of day-to-day operational truth and cannot be ignored by Polaris.

Current pilot:
- Microsoft Teams has been started in parallel with 2 drivers plus Dispatch and Maintenance groups;
- the plan is to test before moving the wider workforce.

Current strategic view:
- Teams is preferred if the pilot succeeds because it provides an official Microsoft enterprise integration path and fits the existing Outlook/Microsoft ecosystem;
- do not move all drivers yet;
- evaluate driver adoption, notifications, photo/document handling, response speed, searchability and official Polaris ingestion;
- operational messages should not be duplicated indefinitely across both platforms during the pilot because that prevents a realistic test.

WhatsApp Business investigation:
- distinguish the WhatsApp Business App from the WhatsApp Business Platform / Cloud API;
- production API uses official Meta business credentials/tokens rather than a simple consumer-style API key;
- test using official supported mechanisms/test numbers before touching the existing operational setup;
- do not build Polaris on unofficial WhatsApp Web scraping, reverse-engineered libraries or fragile personal-device sessions;
- determine whether official WhatsApp group capabilities can support MOR's real operational group sizes and governance needs before making any migration decision.

Decision remains open until the pilot and official API feasibility are tested.

## Pre-Track 4D gates

1. Stabilize existing five operational sources:
   - continued TorqueAI hourly schedule reliability after the first successful natural Stage 2 run;
   - Motive daily scheduler health;
   - ACE daily feed health;
   - QuickBooks critical reconciliation;
   - Outlook general mailbox/attention confidence.
2. Implement Fuel Connector V1 after official supplier API/feed access is available.
3. Finalize the Teams-vs-WhatsApp internal-communications architecture based on pilot evidence.
4. Begin Track 4D cross-connector intelligence.

## First Track 4D products

### Load Risk / Dispatch Control
TorqueAI + Motive + Outlook/internal communications.

### Cash & Customer Risk
QuickBooks + TorqueAI + Outlook.

### Bond / Cross-Border Risk
ACE + TorqueAI + Outlook/internal communications.

### Fuel Cost / Plan Compliance Risk
Fuel supplier data + TorqueAI + Motive + internal communications.

## Owner Alpha safety boundary

Polaris should first become excellent at:

`Observe -> Correlate -> Explain -> Prioritize -> Recommend`

Do not yet make the Owner Alpha automatically:
- send external email/chat;
- change loads;
- make QBO entries/payments;
- resolve ACE matters;
- approve bond use;
- authorize fuel purchases;
- execute other material provider actions.

Later progression, after trust is established:

`Recommend -> Ask for approval -> Execute governed action`

## Strategic principle

Do not measure progress primarily by connector count.

Measure:

> How many important things MOR management currently has to discover manually across separate systems can Polaris identify, explain and prioritize automatically?

## Suggested next conversation sequence

1. Verify current GitHub/main and any scheduled connector runs before making changes.
2. Review this handoff and `docs/engineering/PRE_TRACK_4D_OWNER_ALPHA_DIRECTION.md`.
3. Continue the Teams pilot and WhatsApp official API feasibility discussion until the communications direction is finalized.
4. Do not begin major connector expansion until the owner decides the immediate next course.
5. Once direction is confirmed, convert the chosen work into a narrow design/build/verify PR sequence.