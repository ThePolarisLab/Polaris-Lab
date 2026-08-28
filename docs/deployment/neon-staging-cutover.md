# Neon Staging Database Cutover

Status date: 2026-08-28

## Goal

Run the Polaris staging API on Render's free web service while using an external Neon PostgreSQL database, so the active staging database no longer expires with Render's 30-day free PostgreSQL limit.

## Render Blueprint

`render.yaml` keeps `polaris-executive-api` on the Render free web-service plan and treats `DATABASE_URL` as an operator-supplied secret (`sync: false`). The existing expired `polaris-staging-db` remains declared on the free plan temporarily so the current grace-period recovery option is preserved while the API is cut over to Neon.

## Cutover Steps

1. Create a Neon PostgreSQL project/database.
2. Copy the Neon PostgreSQL connection string.
3. In Render, open `polaris-executive-api` > Environment and replace `DATABASE_URL` with the Neon connection string.
4. Keep all existing Polaris/Motive/Outlook/QuickBooks secrets unchanged.
5. Deploy the API.
6. Confirm startup runs `python -m alembic upgrade head` successfully.
7. Confirm `GET /health` returns HTTP 200.
8. Bootstrap staging organization/admin data as required for a fresh database.
9. Reauthorize integrations whose authorization state was stored only in the old database.

## Old Render Database

Do not delete the expired `polaris-staging-db` during the grace period. It can still be temporarily upgraded and exported if historical staging data is later required before Render's deletion deadline.

After the grace period is no longer needed, remove the old Render database from the Blueprint in a separate reviewed change.

## Safety Notes

- Never commit the Neon connection string or any `.env` file.
- Preserve the existing token-encryption keys when reconnecting integrations.
- Treat the fresh Neon database as empty until Alembic migrations complete successfully.
