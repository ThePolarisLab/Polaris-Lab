# Polaris Track 4C: Motive Roadmap

## 4C.1A: OAuth Production Foundation

- Add canonical Python Motive boundary in `chief-of-staff/`.
- Persist encrypted organization-scoped OAuth access and refresh tokens.
- Add one-use organization-scoped OAuth state persistence.
- Add tenant-owned Motive foundation tables and schema inventory.
- Add normalized internal contracts for vehicles, driver identity, vehicle utilization, driver utilization, and IFTA summary.
- Add limited read-only OAuth verification only.

## 4C.1B: Provider Contract Completion

Blocked until Motive confirms:

- exact rate-limit contract
- complete driver-list contract
- production-safe retry and pagination behavior
- token revocation endpoint availability, if remote revocation is required

## Later Tracks

- broad synchronization and reconciliation
- webhooks with delivery audit trail and dead-letter handling
- executive fleet KPIs
- frontend fleet dashboard
- HOS, safety, DVIR, fault codes, trips, maintenance, and fuel purchases
