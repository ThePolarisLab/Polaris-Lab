# Knowledge base: Motive first production vehicle-utilization ingestion

Status: SUCCESS — manual production proof complete
Date: 2026-08-19

## Certified result

The first controlled production ingestion for `GET /v1/vehicle_utilization` completed successfully through Polaris.

Sanitized result:

- HTTP 200 / `status: success`
- 7 completed `America/Chicago` daily windows
- 23 selected vehicles
- 7 provider calls attempted / 7 completed
- 72 provider rollups returned
- 89 requested-vehicle omissions
- 11 records inserted
- 61 records updated
- 0 unchanged records
- 181 reconciled fields
- checkpoint advanced
- sync history written
- scheduler disabled
- no failed units
- no secrets exposed

## Production semantics retained

- dates are local calendar dates in `America/Chicago` with timezone rules;
- `end_date` is inclusive;
- production requests explicitly use `X-Metric-Units: false`;
- returned unit context must remain compatible with imperial mode;
- fuel is interpreted as gallons under the certified request/response unit context;
- no unit conversion;
- missing provider rollups remain omissions only and must never be converted to zero/inactive rows.

## Safety state after run

After the successful one-attempt execution, both production flags were returned to false and Render was confirmed live:

```text
MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_INGESTION_ENABLED=false
MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED=false
```

The successful request must not be rerun under the same authorization.

## Next boundary

No scheduler is authorized yet. A scheduler must be designed, implemented, reviewed, tested, and gated separately. Motive Company API Key rotation remains mandatory before broad/scheduled production enablement.
