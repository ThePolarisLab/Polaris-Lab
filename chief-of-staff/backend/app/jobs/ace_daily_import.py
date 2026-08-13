"""Render Cron entry point for the ACE daily Outlook feed."""

from __future__ import annotations

import json
import logging

from app.ace.feed_runner import AceFeedConfigurationError, resolve_configured_organization, run_ace_daily_import
from app.database.database import SessionLocal

logger = logging.getLogger(__name__)


def main() -> int:
    with SessionLocal() as db:
        try:
            organization = resolve_configured_organization(db)
            result = run_ace_daily_import(db, organization.id, mode="automatic")
        except AceFeedConfigurationError as exc:
            logger.error("ACE daily import configuration failed", extra={"operation": "ace_daily_import", "status_category": str(exc)})
            print(json.dumps({"status": str(exc), "secrets_exposed": False}))
            return 2
    print(json.dumps({
        "status": result.status,
        "source_found": result.source_found,
        "replayed": result.replayed,
        "records_read": result.records_read,
        "records_inserted": result.records_inserted,
        "records_updated": result.records_updated,
        "exceptions_created": result.exceptions_created,
        "secrets_exposed": False,
    }, default=str))
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
