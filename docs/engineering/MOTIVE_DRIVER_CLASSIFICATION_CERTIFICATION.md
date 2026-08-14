# Motive Driver Classification Certification

This Fleet Operations V1 certification covers a narrow computed classification over the existing `GET /v1/users` ingestion contract.

It certifies only this statement:

```text
provider_payload_metadata.role == "driver" -> Motive driver-role user
```

It does not certify:

- MOR business driver
- MOR employed driver
- MOR active driver
- available driver
- dispatched driver
- HOS-ready driver
- currently working driver
- assigned vehicle driver

## Provider Evidence

Official Motive documentation for `GET /v1/users` states that the endpoint returns company users and documents role concepts/values including:

- `driver`
- `fleet_user`
- `admin`

Motive also documents a `role` query parameter with possible values `driver`, `fleet_user`, or `admin`.

## Persisted Source

Polaris currently persists `/v1/users` rows in the historical `motive_drivers` table. That table stores Motive company users, not certified MOR drivers.

The classification source is:

```text
MotiveDriverRecord.provider_payload_metadata["role"]
```

No migration is required.

## Classification Model

| Computed classification | Rule | Meaning |
| --- | --- | --- |
| `motive_driver_role` | role normalizes to `driver` | The Motive user row has provider role `driver`. |
| `motive_non_driver_role` | role normalizes to `fleet_user` or `admin` | The Motive user row has a recognized non-driver provider role. |
| `unknown_role` | role is missing, blank, non-string, or undocumented | Polaris must not classify the row as a Motive driver-role user. |

Normalization is limited to trimming surrounding whitespace and lowercasing a string value before matching the documented role values. Compound structures such as `roles[]` are not used for certification.

## Read API

`GET /api/v1/motive/fleet/driver-classification`

The endpoint is authenticated, organization-scoped, and read-only. It returns:

- total persisted `/v1/users` rows;
- rows with role;
- Motive driver-role count;
- recognized non-driver-role count;
- missing/unknown-role count;
- undocumented-role count;
- classification definitions;
- certification and safety flags.

It does not return names, email addresses, usernames, phone numbers, provider user IDs, raw metadata, raw provider payloads, headers, credentials, or secrets.

## Active Driver Safeguard

Even when:

```text
role == "driver"
status == "active"
```

Polaris must not infer:

```text
MOR active driver = true
```

Motive role and status are certified only as provider literals. MOR employment, availability, dispatch, HOS, and current working state remain deferred.

## Vehicle-Driver Association

Vehicle-driver association remains deferred. This classification does not assign vehicles and must not be used to infer current vehicle assignment.

## Dashboard / Daily Brief Boundary

The classifier does not create Motive Dashboard cards, Daily Brief attention, operational alerts, or driver exceptions. Fleet attention remains deferred until separate operational semantics are certified.
