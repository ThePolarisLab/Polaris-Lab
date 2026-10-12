# Polaris / MOR Governed Business Rules — Baseline v1.0

Status: **CONFIRMED MOR RULES**, with separately identified **TECHNICAL RECOMMENDATIONS** and **OPEN/FUTURE ITEMS**.

Recorded: 2026-10-11 (America/Toronto). Authority: Surinder / MOR owner, through the explicit instructions to establish this governed repository baseline. Scope: development, analytics, reconciliation, AI reasoning and future automation.

This baseline follows the [Polaris Constitution](../governance/POLARIS_CONSTITUTION.md) and preserves the [Fuel Intelligence Constitution](POLARIS_FUEL_INTELLIGENCE_CONSTITUTION.md). [PROJECT_STATE](../../PROJECT_STATE.md) records implemented capability and certification boundaries. Business approval does not establish implementation, deployment or technical certification. This document authorizes no runtime, schema, integration, provider, production-configuration or operational-write change.

## CONFIRMED MOR RULES

### 1. Governance authority

Only Surinder / the MOR owner may change Polaris vision, core business rules, operating policy, automation authority or consequential decision boundaries. Other users act only within their assigned roles and permissions. Developers, AI models and users must not infer new business rules from system behavior. Material ambiguity requires stopping the affected decision or action and obtaining human clarification.

### 2. Operational history

The latest verified value represents current operational truth at a point in time. Important changes must retain old value, new value, timestamp, source/system, user/person where available and reason if known.

Priority fields include customer, shipper, receiver, rates, charges/deductions, appointments, equipment/driver assignments, mileage, status, invoices, compliance data and documents. This applies to any field affecting operations, customer service, driver instructions/pay, billing, compliance, profitability, audit or Polaris reports. Meaningful history must not be silently overwritten.

### 3. Customer, shipper and receiver history

Retain customer identity, address, contact and billing details; shipper identity, address, contact and pickup instructions; receiver identity, address, contact and delivery instructions; references, commodity, weight, temperature and special instructions. Important changes preserve history under rule 2.

### 4. Pickup and delivery appointments

Preserve original load-confirmation dates/times, TBD state, later confirmed appointments, revised appointments, current effective appointment, actual arrival, waiting/loading/unloading where available, completion and departure. Retain source and reason where known. Significant timestamp conflicts require human confirmation. Small differences may describe arrival, waiting, loading, completion or departure rather than errors; do not invent a numeric tolerance or collapse distinct events.

### 5. Permanent tractor identity

VIN is the permanent physical tractor identity. MOR truck/unit number is a business/operational identifier and may be reused for a different physical tractor after sale/return, for example to use plate fees. Historical fuel, MPG, maintenance, utilization and profitability must respect VIN plus effective time period, not unit number alone.

Preserve VIN, MOR unit, plate, effective-from/to, ownership/lease period and Motive provider/vehicle ID where available. Identity ambiguity requires human confirmation.

### 6. Trailer identity

MOR generally retains a trailer's MOR unit number permanently for that physical trailer and does not intentionally reuse it after sale/return. A leased trailer may have both MOR and vendor/lessor identifiers: `MR021 2R0276` or `MR011 R30388`, for example. Adding a vendor ID is identity enrichment, not automatically reassignment. Physical identity and history must remain traceable. Future field separation is a technical recommendation below.

### 7. Active and inactive roster

Active means the real MOR driver/equipment roster as of the report date. When a driver leaves or equipment is sold, returned or deactivated, preserve historical facts and mark inactive with effective dates. Never delete history to reflect inactivity. TorqueAI and Motive should normally agree on the current roster; disagreement is a data-maintenance exception requiring human review.

### 8. TorqueAI and Motive authority

TorqueAI is primary for loads, customers, pickup/delivery, load assignments, assigned driver, tractor/trailer, load status, appointments and customer billing intent. Motive is stronger operational evidence for actual driver ELD login, HOS/duty status, fresh telematics/current movement/location and device activity.

On disagreement, flag immediately, show both sources with timestamps and use Motive ELD login as stronger evidence of who is actually operating the vehicle. Obtain human confirmation before correcting records. No silent overwrite; stronger evidence does not itself authorize a correction.

### 9. Border-load reconciliation

For border shipments, also cross-check ACE manifest and BorderConnect. Material assignment or identity discrepancies must be escalated and human-confirmed before correction.

### 10. TorqueAI status semantics

The normal operational sequence is `Unassigned -> Assigned -> Loaded -> In Transit -> Delivered`. Billing progression includes `Not Invoiced -> Sent`. `Sent` means delivered plus invoiced.

Staff may skip intermediate statuses: `Assigned`, `In Transit` or `Delivered` transitioning to `Sent` can be legitimate when delivery and invoicing are complete. Once `Sent`, later factoring/payment activity does not change TorqueAI load status.

### 11. Cancelled, Hold and VOID identity safety

`Cancelled` means the load will not execute in its current form; TorqueAI retains it for audit and moves it to historical. `VOID - <order>` is meaningful cancelled/voided evidence and must never be stripped or automatically merged. Order/load numbers can sometimes be reused. `Hold` may later resume or be repurposed.

Reuse or continuation from `Cancelled` or `Hold` requires human confirmation. This is a hard identity-safety rule, including when a reused number resembles an existing record.

### 12. Loaded miles

TorqueAI initially calculates loaded miles from Google Maps. A driver may later report an operationally necessary route difference; MOR may approve corrected loaded miles. The latest MOR-approved loaded miles are authoritative for driver pay, costing, historical reporting and profitability. Preserve original mileage, revised mileage, difference, reason, approving source/user and timestamp. A driver report alone does not establish MOR approval.

### 13. TorqueAI invoice authority

Customer invoices are created and revised in TorqueAI. Any rate, charge, deduction or invoice-amount change must be corrected in TorqueAI first, a revised invoice generated, then reflected in QuickBooks.

### 14. QuickBooks authority and limits

QuickBooks is authoritative for later accounting activity after invoice creation: payments, factoring activity/fees, receipts, deductions, settlements and other post-invoice accounting. Factoring rejection does not alter TorqueAI load status.

Initial Polaris authority is read, analyze, reconcile and prepare entries for approval. Future posting requires separately approved automation. This business boundary does not claim entry preparation is already implemented or certified.

### 15. Fuel governance

Preserve the existing [Fuel Intelligence Constitution](POLARIS_FUEL_INTELLIGENCE_CONSTITUTION.md). Supplier quoted/billed price and quantity evidence remain distinct from Motive corroboration. Motive may corroborate truck, quantity, location and operational fueling evidence, but its fuel price must not replace supplier price evidence for supplier reconciliation.

Discrepancy flow: flag -> explain -> notify human -> human decides. Preserve historical station, supplier, network, route, pricing, truck-access, reefer-fuel and repair-support information.

### 16. Repair and route intelligence

Preserve historical truck-stop, workshop, heavy-duty repair, reefer repair and route-support information. MOR uses both Carrier Transicold and Thermo King; future reefer support must include both.

### 17. ACE and bond exceptions

On suspected unauthorized bond use or a serious ACE/bond exception, preserve evidence, raise a critical alert, notify management and support investigation. External escalation to customers, brokers, CBSA, sureties or other parties requires human approval. ACE provider status and MOR internal review status remain separate.

### 18. Fleet decisions

Polaris gathers evidence and recommends BUY / KEEP / REPAIR / REPLACE / SELL; a human decides. Consider revenue, utilization, MPG, fuel, maintenance, downtime, mileage, age, finance, insurance, driver effects, lane performance and replacement economics. Recommendations must retain evidence and uncertainty.

### 19. WhatsApp authority

WhatsApp remains MOR's primary operational communication channel. Initial Polaris authority is read, summarize, extract, flag and link messages to loads, trucks or drivers when evidence supports the association. No automatic sending initially. Future outbound messaging requires a separate gate; initial authority is not a claim that integration is implemented.

### 20. Ollama and local AI policy

Use Ollama as much as practical to reduce cost, including for operational and financial data, only on secured MOR-controlled infrastructure with required technical, privacy, compliance and safety controls:

- No passwords, tokens, credentials or secrets in prompts.
- No insecure public endpoint; control network access.
- Pin and audit model versions where practical.
- Validate outputs before operational use.
- Minimize necessary logging and apply appropriate retention.
- Require human approval for consequential actions.

Polaris may route lower-risk/simple tasks to Ollama first and use hosted models when task complexity, quality/confidence or policy requires. Provider choice never changes approval boundaries. This is approved provider policy, not an instruction to change current routing or certify an undeployed environment.

### 21. Human-confirmation principle

When material business meaning, conflicting system evidence, Cancelled/Hold reuse, identity ambiguity, significant timestamp differences or consequential operational/accounting/compliance impact is uncertain, Polaris must ask a human rather than invent the answer. Human confirmation resolves the stated ambiguity; any consequential action still needs applicable approval.

### 22. Historical backfill boundary

Surinder's confirmed state for this baseline: [PR #335](https://github.com/ThePolarisLab/Polaris-Lab/pull/335) update-evidence layer is production-certified. The September 1–7 certified preview had 22 provider records: 18 `would_update`, 2 unchanged and 2 identity conflicts/quarantined; zero operational writes. This preserves the owner's supplied certification state; this documentation change does not independently rerun production certification.

The historical writer remains unauthorized. Operational enrichment still needs appropriate field-level evidence before any write execution is considered. Existing quarantined conflicts must remain untouched. Update-evidence certification does not certify operational-enrichment rollback, historical completeness or a write-enabled executor.

### 23. Backup, Restore, and Recovery Governance

**CONFIRMED MOR RULES** — recorded 2026-10-12 (America/Toronto). Authority: Surinder / MOR owner, through the explicit instruction to record these ten recovery requirements before infrastructure action. This revision promotes the previously recommended recovery targets and gates to governing requirements; it does not establish technical capability or certification. The original baseline is preserved in Git history.

1. **Recovery gate:** historical writes or broader autonomy remain blocked until recovery is certified.
2. **Recovery objectives:** target recovery point objective (RPO) <= 1 hour and recovery time objective (RTO) <= 4 hours. These are required certification targets, not achieved service guarantees.
3. **Tested restoration:** certification requires a tested restore with evidence; the existence or readability of backups alone is insufficient.
4. **Production protection:** restore tests must use an isolated non-production environment and must not modify production data.
5. **Original-state integrity:** validate restored data before migrations or upgrades. Preserve tenant isolation, audit history, TorqueAI backfill evidence and the two quarantined identity conflicts; do not resolve, merge or alter those conflicts during recovery testing.
6. **Recoverability verification:** verify the actual production database mapping; Neon backup, PITR, snapshot and export capabilities; independent backup availability; encryption-key and configuration recovery; and documented recovery ownership. Record unavailable or unverified capabilities as gaps, not assumptions.
7. **Containment:** external integrations and side effects must be disabled during restore testing, including schedules, ingestion, provider refresh, outbound communications, financial posting and historical execution.
8. **Evidence:** record timestamps with timezone, elapsed recovery time, measured RPO/RTO and explicit pass/fail against each target, integrity and isolation evidence, and unresolved gaps. Missing evidence must remain visible; a documentation merge or passing CI is not recovery certification.
9. **Cloud approval:** any cloud action that creates or deletes resources, changes production settings, incurs cost, rotates keys or alters backup policy requires explicit human approval before execution. Approval must cover the concrete action and scope; this documentation authorizes none of those actions.
10. **Separate write approval:** historical write execution requires separate explicit approval even after recovery certification. Certification does not grant broader autonomy or waive field-level evidence, identity-safety or execution controls.

Execution planning and certificate evidence belong in the [recovery-readiness assessment and isolated restore plan](../database/RECOVERY_READINESS_2026-10-12.md) and [rollback and recovery runbook](../database/rollback-and-recovery.md). Recovery remains **NOT CERTIFIED**; no infrastructure action is performed by this revision.

## TECHNICAL RECOMMENDATIONS

These recommendations require implementation review and certification. They are not claims of existing capability or authorization to change production.

### Backup and disaster recovery

**TECHNICAL RECOMMENDATIONS** — implementation choices supporting [rule 23](#23-backup-restore-and-recovery-governance), not additional MOR rules or execution authority.

Consider automated backup coverage through PITR or frequent snapshots plus encrypted independent exports, failure/coverage monitoring, secure key/configuration custody and a recurring restore-test cadence. Select frequencies, retention, service tier, export destination and isolation architecture only after verifying actual capabilities, cost and required human approval. The recovery plan proposes separate PITR and independent-export tests; implementation and technical certification remain open.

### Identity and field design

Implement tractor identity/history around VIN, operational identifiers and effective periods. The concrete schema shape, constraints and migrations require separate design and certification.

For trailers, separate MOR trailer number, vendor trailer number, plate and ownership/lease status while allowing a combined display. This future design supports confirmed identity semantics; it does not itself define a migration or authorize reassignment.

## OPEN/FUTURE ITEMS

| Item | Required next evidence or gate |
| --- | --- |
| Operational-enrichment field-level evidence | Appropriate before/proposed field-level evidence and review/rollback sufficiency before any operational write is considered. Fingerprints alone do not close the gate. |
| WhatsApp integration mechanics | Define access, permissions, evidence-based linking, retention and certification for the initial read scope. Outbound messaging needs separate approval. |
| Ollama deployment architecture/certification | Select secured MOR-controlled hosting, network controls, model/version audit, validation, logging/retention and routing criteria; certify before relying on the deployment. |
| Backup/restore certification | Satisfy confirmed rule 23 with tested restore evidence, measured RPO/RTO, ownership and key/configuration recovery; implementation remains unverified. |
| Future write-enabled historical executor | Remains unauthorized; requires separately approved scope, field evidence, identity safety, recovery certification and execution controls. Keep quarantined conflicts untouched. |
| Identity implementation | Review and certify effective-period tractor identity and trailer field separation without inventing business reassignment. |
| Future accounting posting / outbound communication | Separate approved automation gates; neither is enabled by this baseline. |
| Material ambiguities discovered later | Refer to Surinder / MOR owner for business-rule decisions; do not invent thresholds, authority or exceptions. |

## Change control and interpretation

Owner-approved business-rule revisions must record authority, date, changed rule and rationale, preserving the prior baseline in repository history. Technical recommendations and future items must remain visibly separate from confirmed rules. Developers may propose designs but cannot silently promote them to MOR policy. Certification records must state their bounded scope and evidence; a merge alone is not certification.
