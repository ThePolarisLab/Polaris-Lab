# Polaris Pre-Track 4D / Owner Alpha Direction

Status: Proposed strategic direction for human review
Date: 2026-08-29
Owner: Polaris Lab / MOR Logistics
Base main SHA reviewed: `8d46212ba8b13a7f97cb7dc1b8974c23b9d625db`

## Purpose

Record the agreed product direction before Polaris moves from independently trusted connectors into cross-connector executive intelligence and Owner Alpha use at MOR Logistics.

The immediate goal is no longer to maximize the number of isolated integrations. The goal is to make Polaris the first management screen for MOR Logistics while preserving source-system authority and Observer/Advisory mode.

North-star outcome:

> Every morning, the owner should be able to open Polaris first and understand the 3-5 most important items requiring attention across MOR Logistics within approximately five minutes.

## Current project stage

Polaris is in **late Track 4 / pre-Track 4D**.

Infrastructure, authentication, persistent database, CI, migrations, and the principal connector foundations are established. The project is transitioning from:

`Connect -> Verify -> Persist -> Automate`

to:

`Correlate -> Reason -> Prioritize -> Advise`

Track 4D must consume only trusted, normalized, tenant-scoped records. Raw provider objects must not become the executive intelligence contract.

## Seven strategic evidence streams

Polaris should treat the following as the principal evidence streams required for MOR Logistics Owner Alpha.

### 1. TorqueAI - Dispatch / loads

Role:
- loads and dispatch activity;
- shipment/stops/billing context available from the approved external dispatch contract;
- source for future dispatch exceptions and cross-source load correlation.

Current position:
- production connector certified;
- durable dispatch ingestion implemented;
- durable read API and Dispatch dashboard implemented;
- successful production certification on 2026-08-29 validated 31 provider rows: 23 inserted, 1 updated, 7 unchanged;
- Stage 2 hourly schedule (`17 * * * *`) merged in PR #252;
- first natural post-merge scheduled execution and short-term schedule reliability still require observation.

### 2. Motive - Fleet operations

Role:
- fleet and vehicle evidence;
- utilization/fuel observations;
- future driver, location, HOS, safety, maintenance and related fleet intelligence where contracts are independently certified.

Current position:
- production Company API Key architecture established;
- vehicle and company-user ingestion established;
- durable vehicle-utilization ingestion and checkpointing established;
- daily scheduler established;
- seven-day utilization/fuel read models and multiple fleet KPIs implemented;
- broader Track 4C scope remains incomplete, especially authoritative driver classification, vehicle-driver association, location, HOS, safety and maintenance intelligence.

Decision:
- do not expand Motive simply because another endpoint is available;
- add broader Motive capabilities when a concrete Owner Alpha / Track 4D use case requires them.

### 3. Fuel suppliers - Fuel cost, fueling plan and invoice control

Role:
- current/contracted fuel pricing by location;
- actual fueling quantity and amount;
- route fueling recommendations;
- actual-versus-plan compliance;
- supplier invoice reconciliation;
- detection of quantity and pricing discrepancies.

Business reason:
Fuel is a major MOR Logistics operating cost, fuel prices are volatile, and historical supplier invoicing discrepancies have occurred in both quantity and price. Fuel is therefore a first-class business-control evidence stream, not an optional KPI.

Proposed Track 4E - Fuel Intelligence & Control:

V1 target:
- supplier transaction ID;
- timestamp;
- station/location and supplier location ID;
- gallons/litres;
- product/grade;
- posted/base price if available;
- MOR contracted/net price if available;
- taxes/fees;
- total amount;
- truck/unit/card/driver references where available;
- invoice/reference number;
- current station price feed where supplier supports it.

V1 acceptance outcome:
> Polaris can independently compare what MOR bought with what MOR was charged and surface price/quantity exceptions without changing supplier systems.

Later target:
- route-aware fueling plans using dispatch route, truck/fuel context, safe reserve, supplier prices/discounts and approved business rules;
- actual-versus-plan monitoring;
- avoidable-cost estimates;
- owner/dispatch attention for meaningful deviations.

### 4. Outlook - External business communication

Role:
- customer, broker, supplier, financing, compliance and other external communication evidence;
- read-only classification and executive attention;
- attachment/provenance support for workflows such as ACE.

Current position:
- Track 4B read-only connector architecture implemented and merged;
- delegated `Mail.Read` boundary, tenant ownership, persistence, checkpoints, classification and executive attention architecture exist;
- Outlook access is sufficiently operational for ACE daily-report ingestion;
- full general-mail production validation and owner-quality attention behavior still require confidence testing.

### 5. Internal communications - Teams preferred strategic path, WhatsApp under feasibility test

Role:
- driver operational updates;
- dispatch/back-office coordination;
- workshop/maintenance evidence;
- safety/compliance communication;
- accounting/management decisions and approvals.

Current operational reality:
- WhatsApp groups are a major day-to-day source of MOR Logistics information;
- management and operational teams currently rely heavily on WhatsApp;
- Polaris would have a material blind spot if internal operational communication is excluded.

Current decision state:
- no final migration decision yet;
- Microsoft Teams pilot has started in parallel with 2 drivers plus Dispatch and Maintenance groups;
- pilot should be tested before broad migration;
- Teams is the preferred long-term architecture if the pilot confirms adoption/reliability because it provides an official Microsoft enterprise integration path and fits the existing Microsoft/Outlook ecosystem;
- WhatsApp Business Platform / Cloud API feasibility should be tested separately using official supported mechanisms and without risking existing operational groups;
- do not base Polaris production architecture on unofficial WhatsApp Web scraping, reverse-engineered libraries or fragile personal-device sessions.

Pilot success questions:
- will drivers actually use Teams consistently?
- are notifications, photos and documents reliable on mobile?
- can Dispatch and Maintenance respond as quickly as current WhatsApp operations?
- is operational history easier to retrieve?
- can Polaris ingest approved Teams communications through an official, governed integration?

Migration principle:
- do not move all drivers until pilot evidence is positive;
- do not duplicate every message indefinitely across WhatsApp and Teams, because that prevents a realistic pilot;
- if Teams succeeds, migrate in controlled phases and retain WhatsApp temporarily as transition/emergency fallback.

### 6. ACE - Customs / bond control

Role:
- MOR carrier/bond exposure;
- in-bond movement lifecycle;
- authorized/unauthorized review;
- filer/carrier exceptions;
- overdue/late/closure monitoring;
- Daily Brief management attention.

Current position:
- core ACE V1 workspace and durable persistence implemented;
- search, filters, counters, history, authorization, resolve/reopen and exception management implemented;
- Outlook XLSX daily-feed importer implemented;
- scheduled GitHub wakeups and replay/idempotency safeguards implemented;
- Daily Brief ACE attention implemented;
- standalone Manifest ingestion and direct CBP automation remain deferred by design.

### 7. QuickBooks Online - Financial truth

Role:
- financial System of Record;
- executive financial snapshots;
- future financial exceptions and customer/vendor financial risk correlations.

Current position:
- production OAuth, Mor Logistics company verification and read-only synchronization are complete;
- Revenue and Total Expenses have been reconciled;
- Accounts Receivable, Accounts Payable, Gross Profit, Net Income and Cash Position still require final reconciliation/mapping confidence;
- remaining work is financial intelligence/reconciliation, not basic connector connectivity.

## Pre-Track 4D readiness gates

Before declaring Owner Alpha ready, focus only on the following gates.

### Gate 1 - Stabilize existing trusted sources

- observe the natural TorqueAI hourly schedule after Stage 2 merge and establish short-term reliability;
- confirm Motive daily ingestion remains healthy;
- confirm ACE daily feed remains healthy;
- complete the important QuickBooks reconciliation needed to avoid misleading executive financial information;
- confirm general Outlook production synchronization/attention behavior, not only ACE-specific mail access.

### Gate 2 - Fuel Connector V1

- obtain official API/feed access from principal fuel suppliers where available;
- implement read-only transaction/price ingestion with tenant isolation, checkpoints, sync history and provenance;
- reconcile supplier transactions against invoice facts;
- surface quantity/price mismatches;
- defer route optimization until the transaction and pricing evidence is trusted.

### Gate 3 - Internal communications architecture decision

- run the Teams pilot with the current small group;
- test official WhatsApp Business Platform feasibility separately without disrupting existing operations;
- make a documented decision based on reliability, adoption, API/governance fit and Polaris evidence requirements;
- if Teams wins, design channels, permissions, identities and migration before broad cutover.

### Gate 4 - Track 4D cross-connector intelligence

Initial cross-source products should be practical MOR management problems, not generic AI features.

#### A. Load Risk / Dispatch Control

Candidate evidence:
- TorqueAI + Motive + Outlook/internal communications.

Outcome:
- detect conflicts such as active loads with truck/service/appointment/communication risk;
- explain the supporting evidence;
- recommend owner/dispatch review.

#### B. Cash & Customer Risk

Candidate evidence:
- QuickBooks + TorqueAI + Outlook.

Outcome:
- combine financial exposure with current/recent business and payment communication;
- identify owner/accounting follow-up priorities.

#### C. Bond / Cross-Border Risk

Candidate evidence:
- ACE + TorqueAI + Outlook/internal communications.

Outcome:
- identify in-bond movements without expected dispatch/closure evidence;
- identify possible unauthorized bond/carrier-code use;
- prioritize verification before penalties/escalation.

#### D. Fuel Cost / Compliance Risk

Candidate evidence:
- Fuel supplier + TorqueAI + Motive + internal communications.

Outcome:
- compare planned/expected fueling with actual fueling;
- identify high-cost or unplanned purchases;
- identify possible transaction/invoice discrepancies;
- explain the source evidence before recommending action.

## Owner Alpha operating boundary

Owner Alpha remains **Observer / Advisory mode**.

Polaris may:
- ingest approved read-only evidence;
- correlate trusted normalized records;
- prioritize attention;
- explain why an item matters;
- recommend an action;
- allow internal Polaris notes/actions to be recorded.

Polaris must not, during Owner Alpha unless separately authorized and governed:
- send/reply/forward email automatically;
- modify provider loads;
- create accounting entries or payments;
- resolve ACE/CBP matters automatically;
- send operational chat messages automatically;
- approve bond use;
- authorize fuel transactions;
- take other material external actions.

## Owner Alpha success criteria

The first usable MOR Owner Alpha is successful when:

1. The owner can sign in to a stable hosted Polaris Executive Workspace.
2. Principal source health and last-success state are visible.
3. Daily Brief surfaces the 3-5 highest-value management items rather than raw connector noise.
4. Each important item is traceable to its source evidence.
5. Polaris distinguishes fact, correlation, inference and recommendation.
6. Important decisions remain human-approved.
7. Polaris is run side-by-side with existing MOR procedures for at least five business days.
8. Missed or misleading items from the pilot become targeted backlog items.
9. New connector scope is added because a real management question cannot be answered, not merely because an API endpoint exists.

## Product principle going forward

The relevant success metric is no longer "How many APIs are connected?"

The relevant metric is:

> How many important things that MOR management currently has to discover manually across separate systems can Polaris identify, explain and prioritize automatically?

This document is a strategic direction record. It does not itself authorize production mutations, connector scope expansion, migration of all employees to Teams, or automatic external actions.