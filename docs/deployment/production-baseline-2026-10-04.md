# Production baseline evidence — 2026-10-04

This dated register supports [PROJECT_STATE](../../PROJECT_STATE.md). Observations are bounded to the inspection date and evidence source. It does not deploy, restore, change secrets or remove infrastructure. Private infrastructure identifiers, account/owner details and signed-in dashboard URLs are intentionally omitted from this public record; resource names and dated observations retain the verification boundary.

## Release and runtime provenance

| Observation | Source and limit |
| --- | --- |
| GitHub `main`: `e4775e094e36e0a6b413b1aab2cf35289a1ed6dc` | [Commit](https://github.com/ThePolarisLab/Polaris-Lab/commit/e4775e094e36e0a6b413b1aab2cf35289a1ed6dc), main branch API read 2026-10-04; latest merge #327. |
| Render API `polaris-executive-api`, Free/Python 3/Oregon | Signed-in Render service and deployment pages inspected 2026-10-04. |
| Live API deployment at the same SHA | Render deployment page inspected 2026-10-04: manually deployed 2026-10-03 04:05:45 EDT; reported duration 1m34s. Logs show PostgreSQL Alembic context, upgrade-before-Uvicorn startup, completed startup and `/health` HTTP 200. Logs did not print the live migration revision. |
| Render workspace inventory: two active services, zero suspended | API plus static `polaris-executive`; no Render PostgreSQL resource listed in the inspected workspace. Frontend deployed SHA not verified. |
| Blueprint-managed API | Repository `render.yaml` contains the old PostgreSQL declaration and operator-supplied `DATABASE_URL`. Inventory absence is not proof that Blueprint reconciliation/removal is safe. |

## Database provenance

Signed-in Neon Console inspected 2026-10-04:

- Polaris Neon project: Free, AWS US West 2/Oregon, PostgreSQL 18; private project identifier/name omitted.
- Default branch: created 2026-08-28, never expires. One branch, one database, one compute reported; private branch/database identifiers and names omitted.
- Tables browser: `public.alembic_version` contains one row, **`202609120002`**. This matches the checked-in migration head. Reading the table did not modify data.
- Other account projects are outside this Polaris baseline.

**Evidence limitation:** Render logs prove PostgreSQL use; Neon contains current Polaris schema/data. The Render database secret's hostname/branch target was not independently inspected. Record that relationship as requiring direct operator verification, not an inferred credential mapping. Project/branch labels do not certify staging/production separation.

## Recovery status — material operational risk

The signed-in Neon Backup & Restore page inspected 2026-10-04 displayed **six-hour history window** and **“No snapshots, no schedule set.”** No restore action was performed. No successful isolated restore drill or independently restorable export was verified.

This limits recovery from delayed corruption, deletion or unnoticed credential/state loss. Do not label PITR availability as tested recovery. Follow-up must establish acceptable recovery point/time objectives, independent retention/export feasibility and safe custody of required encryption keys, then restore into an isolated target and validate migrations, tenant boundaries and representative records. Record date, recovery point, elapsed restore time and validation outcome. Avoid publishing credentials or business records in evidence.

## Certification provenance

- [Issue #323](https://github.com/ThePolarisLab/Polaris-Lab/issues/323): accepted 2026-10-03 Auth0/private MCP pickups and loaded trailers.
- [PR #326](https://github.com/ThePolarisLab/Polaris-Lab/pull/326), [PR #327](https://github.com/ThePolarisLab/Polaris-Lab/pull/327): merged lane analytics and dedicated scope; live certification not recorded.
- [Motive fault run 37104948375](https://github.com/ThePolarisLab/Polaris-Lab/actions/runs/37104948375): completed 2026-10-03; 924 faults, 897 closed/27 open, temporal checks valid. Stable identity and observed transition gates false; durable fault memory false. See unresolved [issue #325](https://github.com/ThePolarisLab/Polaris-Lab/issues/325). Repeating a successful snapshot workflow cannot itself prove a transition.
- Current bounded feed results and limitations are listed in [PROJECT_STATE](../../PROJECT_STATE.md); retain underlying historical reports unchanged.

## Historical PR disposition

[PR #134](https://github.com/ThePolarisLab/Polaris-Lab/pull/134) and [PR #137](https://github.com/ThePolarisLab/Polaris-Lab/pull/137) are documentation drafts for dated EOD logs. This replacement preserves their original file contents after a historical-context notice. No merge of their stale status is needed. **Close both as superseded only after this replacement PR is merged**, linking the merged replacement and preserved logs. They remain open during review; no closing keywords are used here.
