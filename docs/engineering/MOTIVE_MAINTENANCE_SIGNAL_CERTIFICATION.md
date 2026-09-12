# Motive Maintenance Signal Certification

## Goal

Create a production evidence gate for Maintenance Readiness before any Motive maintenance data affects dispatch decisions.

## Public provider contract used

Motive's current public API documents:

- `GET /v1/fault_codes` for vehicle diagnostic trouble codes. Documented fields include code/status, first and last observed timestamps, occurrence counts, FMI/DTC metadata, severity, and associated vehicle/gateway objects.
- `GET /v2/inspection_reports` for vehicle inspection reports. Depending on the fleet's Motive inspection configuration, inspected parts may include defects, defect severity, and resolution/mechanic information.

The certification implementation intentionally does not assume that every documented field is present for MOR. Production evidence must establish the actual response structure available to this account.

## Certification behavior

The manual certification gate:

1. reads only a bounded seven-day window;
2. requests at most five rows per maintenance resource;
3. records only JSON schema paths and runtime types;
4. returns no provider values, vehicle identities, fault values, defect text/notes, signature URLs, raw payloads, or credentials;
5. performs no persistence and no provider write;
6. does not change Maintenance Readiness or Assignment Intelligence.

## Resources

- Fault codes: `/v1/fault_codes`, `start_date`, `end_date`, `per_page=5`, `page_no=1`.
- Inspection reports: `/v2/inspection_reports`, `updated_after`, `entity_type=vehicle`, `per_page=5`, `page_no=1`.

The workflow is manual-only and calls the signed Polaris production endpoint. The workflow never receives the Motive API key.

## What remains deferred

Until a successful production certification run is reviewed, Polaris must not:

- interpret specific fault severities as dispatch blockers;
- infer that an inspection defect is unresolved unless the production schema and status semantics support that conclusion;
- calculate a maintenance score;
- auto-mark a vehicle `ready` or `not_suitable` from maintenance data;
- write back to Motive Maintenance, inspection reports, or dispatch systems.

The next phase should normalize only the production-certified fields, then add a conservative maintenance-readiness advisory with explicit evidence and human approval.
