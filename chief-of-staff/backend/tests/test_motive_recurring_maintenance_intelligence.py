from __future__ import annotations

from datetime import date

from app.motive.maintenance_readiness import maintenance_readiness_for_trucks

DAY = date(2026, 9, 12)


def _row(result, truck):
    return next(row for row in result["classifications"] if row["truck_number"] == truck)


class RecurringInspectionConnector:
    def _request_json(self, endpoint: str, *, params: dict, operation: str):
        if endpoint == "/v1/fault_codes":
            return {"fault_codes": [], "total": 0}
        rows = []
        for index, day in enumerate(range(7, 12)):
            rows.append(
                {
                    "inspection_report": {
                        "vehicle": {"number": "M2214"},
                        "is_rejected": False,
                        "date": f"2026-09-{day:02d}",
                        "time": f"2026-09-{day:02d}T15:00:00Z",
                        "inspection_type": "pre_trip",
                        "status": "open",
                        "odometer": 690000 + index * 500,
                        "inspected_parts": [
                            {
                                "category": "18 - Lamps/Reflectors",
                                "type": "minor",
                                "status": "open",
                                "defects": [],
                            }
                        ],
                    }
                }
            )
        return {"inspection_reports": rows, "total": len(rows)}


def test_recurring_open_parts_are_grouped_without_changing_readiness():
    result = maintenance_readiness_for_trucks(
        truck_numbers=["M2214"], as_of_date=DAY, connector=RecurringInspectionConnector()
    )
    row = _row(result, "M2214")
    assert row["classification"] == "verify"
    assert row["open_inspection_part_count"] == 5
    assert row["recurring_inspection_issue_count"] == 1
    assert row["recurrence_changes_readiness"] is False
    assert len(row["inspection_issue_details"]) == 5
    assert row["recurring_inspection_issue_groups"] == [
        {
            "part_name": None,
            "part_category": "18 - Lamps/Reflectors",
            "part_type": "minor",
            "source_record_count": 5,
            "distinct_report_days": 5,
            "recurring": True,
            "first_seen_date": "2026-09-07",
            "latest_seen_date": "2026-09-11",
            "latest_report_time": "2026-09-11T15:00:00Z",
            "latest_odometer": 692000,
            "latest_part_status": "open",
            "latest_report_status": "open",
            "latest_inspection_type": "pre_trip",
            "consecutive_days_confirmed": False,
            "repair_resolution_confirmed": False,
            "safety_related_confirmed": False,
        }
    ]


class UnidentifiedInspectionConnector:
    def _request_json(self, endpoint: str, *, params: dict, operation: str):
        if endpoint == "/v1/fault_codes":
            return {"fault_codes": [], "total": 0}
        rows = [
            {
                "inspection_report": {
                    "vehicle": {"number": "M2214"},
                    "is_rejected": False,
                    "date": f"2026-09-{day:02d}",
                    "time": f"2026-09-{day:02d}T15:00:00Z",
                    "status": "open",
                    "inspected_parts": [{"status": "open"}],
                }
            }
            for day in (10, 11)
        ]
        return {"inspection_reports": rows, "total": len(rows)}


def test_unidentified_open_parts_are_not_grouped_as_recurring():
    result = maintenance_readiness_for_trucks(
        truck_numbers=["M2214"], as_of_date=DAY, connector=UnidentifiedInspectionConnector()
    )
    row = _row(result, "M2214")
    assert row["open_inspection_part_count"] == 2
    assert row["classification"] == "verify"
    assert row["recurring_inspection_issue_count"] == 0
    assert row["recurring_inspection_issue_groups"] == []
