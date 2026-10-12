# Polaris Recovery Readiness and Isolated Restore Certification Plan

Status: **ASSESSMENT COMPLETE / RECOVERY NOT CERTIFIED / PLAN ONLY**.

Recorded: 2026-10-12 (America/Toronto). Repository baseline: `56b65cfd8a44c2d296cdb542a24749bb86efcb42` ([PR #336](https://github.com/ThePolarisLab/Polaris-Lab/pull/336)). Scope: read-only infrastructure metadata and repository inspection; no backup, restore, database query, migration, deployment or configuration change was performed.

Authority: [MOR rule 23: Backup, Restore, and Recovery Governance](../operations/POLARIS_MOR_GOVERNED_BUSINESS_RULES.md#23-backup-restore-and-recovery-governance), owner-confirmed 2026-10-12. Required certification targets are **RPO <= 1 hour** and **RTO <= 4 hours**, not achieved service guarantees. Historical writes and broader autonomy remain blocked until recovery is certified; historical write execution still needs separate explicit approval afterward. The proposed design below remains **TECHNICAL RECOMMENDATIONS** subject to the confirmed rule.

Governance revision only, based on verified main `fdbcc21167d45e94c10a2ae754c16dbe1080d093` (merged [PR #337](https://github.com/ThePolarisLab/Polaris-Lab/pull/337)). Original assessment observations below are retained, not newly verified. Any cloud action creating/deleting resources, changing production settings, incurring cost, rotating keys or altering backup policy requires explicit human approval before execution. No infrastructure action or historical write is authorized or executed here.

## 1. Evidence and present readiness

| Evidence inspected | Observation | Limit / implication |
| --- | --- | --- |
| Connected Neon project metadata, 2026-10-12 | Matching Polaris project: PostgreSQL 18, AWS US West 2; `history_retention_seconds = 21600` (six hours). | Retained history is not an RPO measurement or a successful restore. Public evidence omits private project identifiers. |
| Neon branch listing, 2026-10-12 | One ready default branch named production; branch protection flag false. | A label does not prove which database Render uses; no isolated recovery target currently appears in this listing. This is database branch protection, distinct from GitHub protection. |
| Neon snapshot listing, 2026-10-12 | Empty list. | No snapshot artifact verified by this inspection. Does not prove absence of an external backup outside the connected account. |
| Neon default-branch snapshot schedule, 2026-10-12 | Empty schedule. | No scheduled snapshots verified. No setting was changed. |
| [2026-10-04 production register](../deployment/production-baseline-2026-10-04.md) | Six-hour history, no snapshots/schedule and no restore drill recorded then. | Historical observations agree with current metadata; runtime-to-database mapping and live schema still require direct verification. |
| [Rollback and recovery runbook](rollback-and-recovery.md) | Manual dump/list and isolated restore guidance exists. | Reading a dump/list is insufficient to certify restoration, key recovery or application usability. No execution certificate found in the reviewed evidence. |
| [Render Blueprint](../../render.yaml) | API starts with `alembic upgrade head`; database URL and connector encryption keys supplied outside Git; legacy Render database declaration remains. | A recovered app must use a compatible pinned commit before startup. Git alone cannot recover secret values or prove current runtime configuration. Blueprint declarations are not live resource evidence. |
| [QuickBooks credentials](../../chief-of-staff/backend/app/connectors/quickbooks_credentials.py), [Outlook credentials](../../chief-of-staff/backend/app/connectors/outlook_credentials.py), [Motive credentials](../../chief-of-staff/backend/app/connectors/motive_credentials.py) | Credential decryption depends on environment-held Fernet keys; Motive can fall back to the QBO key. | Restored encrypted rows without matching keys are not usable connector recovery. Keys were not fetched or printed. |
| [GitHub workflows](../../.github/workflows) reviewed for backup/restore automation | No dedicated production backup/export or restore-drill workflow found. | Repository absence does not establish absence of external jobs. Operator inventory remains required. CI migrations/tests do not certify production-data restoration. |

**Conclusion:** Neither target is certified. Six-hour retention leaves delayed corruption/deletion beyond that horizon uncovered by the inspected history setting. It does not mean six hours of data loss, and it does not prove one-hour recovery-point coverage. Independent backup custody, retention, key/configuration recovery and an end-to-end timed restore remain unverified.

## 2. Gaps and decisions before execution

| Gap | Required resolution / evidence |
| --- | --- |
| Exact production source | Operator verifies Render's active database host/database/branch against Neon, using redacted identifiers in public evidence; records deployed application SHA and live Alembic revision. Do not infer from names. |
| Recoverable points and retention | Verify Neon backup/PITR/snapshot/export capabilities and their availability for the actual production source. Confirm oldest/latest restorable points, coverage gaps and failure alerts. Owner chooses retention covering detection delays; six-hour history alone is insufficient evidence for that choice. |
| Independent copy | Select an encrypted, access-controlled export destination outside the primary database failure domain, with retention, integrity verification and tested retrieval. Repository and disposable runtime disks are unsuitable custody. |
| Recovery-point target | Design backup/PITR coverage so newest successfully recoverable point remains <= 1 hour old, including failures and retry time. A nominal hourly schedule alone does not prove the target. |
| Keys and configuration | Inventory required encryption keys, active key versions, auth/session settings, provider credentials, tenant bindings, callbacks, schedules and endpoint settings in approved secret custody. Record retrieval/rotation ownership without secret values. |
| Ownership | Surinder designates incident decision owner, recovery operator, backup custodian and verifier, plus alternates. Role assignment is open, not implied by this document. |
| Isolation and costs | Approve isolated target, retention/deletion date, access controls, sensitive-data handling and any service cost before execution. Prefer a separate recovery project for independent export recovery; a same-project historical branch tests PITR only. |
| Write prohibition | Keep historical executor unauthorized, quarantined conflicts untouched and restored integrations disconnected from live sources throughout the drill. |

## 3. Proposed recovery design

Use two separately tested paths: retained-history recovery for recent incidents and encrypted independent logical exports for incidents outside that window or loss of primary access. Choose actual frequencies, retention and service tier after verifying capabilities and cost; this assessment changes none of them.

Use direct database connections for logical export/restore. Capture all application schemas, data, migration state and required role/grant/extension dependencies; document any objects not covered by a database dump. Preserve audit/evidence records and tenant boundaries. Do not rely on recovering external supplier/provider data later to reconstruct lost evidence.

Keep backup encryption keys and application decryption keys in approved recoverable secret custody, separate from public artifacts. Document version-to-backup compatibility and access recovery. Loss of a key must be treated as a failed recovery path, not solved by silently replacing it.

Monitor newest usable recovery point, backup failure, retention expiration and restore-test age. A recommended initial drill cadence is after setup and material schema/key/deployment changes, with a recurring cadence chosen by MOR. These are proposals requiring implementation review.

## 4. Isolated drill procedure — execution not authorized by this assessment

1. **Preflight and incident record:** obtain approved target/scope and designated operator/verifier. Record incident simulation time, selected recovery point, source deployed SHA, live schema revision, backup identifier/checksum, key versions and target identity in private evidence. Public report uses aggregate facts and redacted references. Reject any source/target ambiguity.
2. **Contain the test:** create an isolated target with separate credentials. Disable schedules, ingestion, provider refresh, outbound email/WhatsApp, finance posting and historical execution; block external provider/network access. A restored database contains sensitive data and active credential material even when no connector is intentionally invoked. Do not point Render, production DNS or GitHub production workflows at it.
3. **Restore the original state:** for PITR, recover the selected historical point into a new target without replacing/finalizing the production branch. For independent export, retrieve, verify checksum/decrypt and restore to an empty isolated PostgreSQL target. Do not overwrite production or use destructive cleanup commands against a computed production URL.
4. **Validate before migrations:** read restored Alembic state and compare it with the selected recovery point and compatible application commit. Check schema, constraints, tenant ownership, representative row counts and protected evidence. Do not stamp versions or run upgrades merely to make a failed restore appear valid.
5. **Validate business evidence:** compare source-at-recovery-point aggregate manifests and deterministic hashes for dispatch, invoice/fuel/ACE evidence, accounting snapshots, roster/identity periods, audit logs, connector checkpoints and historical-backfill review evidence. Current production counts may differ because new records arrived after the recovery point; document expected differences. Verify both quarantined identity conflicts remain represented without altering them.
6. **Validate key/configuration recovery:** retrieve matching key versions through approved secret custody and test decryption locally without logging plaintext or contacting providers. Verify recoverability of required configuration and tenant/provider bindings. Expired external tokens may legitimately require reauthorization; record that dependency and its recovery-time impact rather than refreshing them during the drill.
7. **Validate application usability:** start a compatible pinned application only after reviewing startup behavior. The current Blueprint upgrades schema automatically: use a reviewed isolated startup procedure that preserves the recovered state for initial validation. Test health, authorized tenant-scoped read views and access-denial cases with restored business evidence; use mocks for external providers. Any upgrade rehearsal happens separately on a disposable copy after original-state validation.
8. **Measure and review:** record elapsed retrieval/provisioning, restore, key/config retrieval, validation and application recovery time. Record recoverable-point age and expected data loss. Retain failures and exception explanations. Operator and verifier submit bounded results to Surinder for acceptance.
9. **Close the drill:** preserve protected evidence, revoke isolated access and follow approved retention/cleanup policy. Cleanup is a separate verified action; do not delete a branch/project autonomously. No production cutover occurs in this drill.

## 5. Pass/fail and certificate

RPO measurement: simulated incident time minus the latest successfully recoverable committed-data point, with explicit timezone and expected excluded records; must be <= 1 hour for the target. Backup start time alone is not the recovery point. Also demonstrate that operational scheduling/alerting sustains coverage, rather than one conveniently chosen backup.

RTO measurement: elapsed time from incident declaration to validated usable application and required configuration/key recovery; include provisioning, artifact retrieval, restore and validation. Must be <= 4 hours for the target. A database restore finishing alone is not application recovery.

Pass requires both targets, record/tenant/evidence integrity, matching-key recovery, compatible schema/application, effective isolation and human acceptance. A recent PITR success does not certify independent export recovery or an incident outside retained history. Missing evidence or any unresolved material integrity issue is FAIL / NOT CERTIFIED, with a documented remediation and repeat drill.

Certificate template (complete only after execution):

| Field | Required evidence |
| --- | --- |
| Drill ID/date and scenario | Incident definition; PITR or independent export; exact tested boundary |
| Authority and people | Approver, operator, verifier and recovery owner |
| Source and target | Privately verified identities; source deployed SHA/schema; isolated target |
| Artifact and point | Recovery point, backup manifest/checksum, retention and key versions; no secret values |
| Timeline | Incident declaration, recovery point, retrieval, restore, validation and usable-app timestamps |
| RPO / RTO | Measured values, elapsed recovery time and sustained-coverage evidence; explicit PASS/FAIL for each governed target |
| Integrity | Aggregate manifests/hashes, tenant/access checks, quarantined conflicts and audit preservation |
| Configuration / keys | Secure retrieval and decryption outcome; reauthorization dependencies |
| Isolation / cleanup | Disabled external actions, target access and approved retention/disposition |
| Result | PASS or FAIL, evidence references, unresolved gaps, failures, remediation, acceptance and next review date |

## 6. Next approval package

Prepare a concrete execution package after resolving source mapping and custody: selected backup method/retention, target/cost, isolation controls, operators, key/config retrieval procedure, exact compatible app/schema and certificate checklist. Seek approval for that bounded drill and any production backup configuration separately. Historical writes remain unauthorized regardless of this plan or a later successful restore.
