from __future__ import annotations

from datetime import date

from app.motive.maintenance_readiness import (
    MAX_DETAILS_PER_TRUCK,
    MAX_PAGES,
    PAGE_SIZE,
    maintenance_readiness_for_trucks,
)

DAY = date(2026, 9, 12)


class FakeConnector:
    def __init__(self, *, fault_total=2, report_total=3, fail=False):
        self.fault_total = fault_total
        self.report_total = report_total
        self.fail = fail
        self.calls = []

    def _request_json(self, endpoint: str, *, params: dict, operation: str):
        from app.connectors.motive import MotiveConnectorError

        self.calls.append((endpoint, params["page_no"]))
        if self.fail:
            raise MotiveConnectorError("unavailable", http_status=503)
        total = self.fault_total if endpoint == "/v1/fault_codes" else self.report_total
        start = (params["page_no"] - 1) * PAGE_SIZE
        stop = min(start + PAGE_SIZE, total)
        if endpoint == "/v1/fault_codes":
            rows = []
            for i in range(start, stop):
                if i == 0:
                    rows.append(
                        {
                            "fault_code": {
                                "status": "opened",
                                "code": "SPN 3226",
                                "code_label": "Outlet NOx",
                                "code_description": "Outlet NOx sensor circuit",
                                "first_observed_at": "2026-09-11T10:00:00Z",
                                "last_observed_at": "2026-09-12T10:00:00Z",
                                "occurrence_count": 2,
                                "observation_count": 4,
                                "fmi": 4,
                                "fmi_description": "Voltage below normal",
                                "dtc_severity": "critical",
                                "vehicle": {"number": "M2209", "vin": "VIN-SECRET"},
                            }
                        }
                    )
                else:
                    rows.append({"fault_code": {"status": "closed", "vehicle": {"number": "OTHER"}}})
            return {"fault_codes": rows, "total": total}

        rows = []
        for i in range(start, stop):
            if i == 0:
                rows.append(
                    {
                        "inspection_report": {
                            "vehicle": {"number": "M2210", "vin": "VIN-SECRET"},
                            "is_rejected": True,
                            "date": "2026-09-12",
                            "time": "09:15",
                            "inspection_type": "pre_trip",
                            "status": "open",
                            "odometer": 123456,
                            "driver_signature_url": "https://secret.example/signature",
                            "inspected_parts": [],
                        }
                    }
                )
            elif i == 1:
                rows.append(
                    {
                        "inspection_report": {
                            "vehicle": {"number": "M2207"},
                            "is_rejected": False,
                            "date": "2026-09-11",
                            "time": "18:30",
                            "inspection_type": "post_trip",
                            "status": "open",
                            "odometer": 555000,
                            "inspected_parts": [
                                {
                                    "name": "Brakes",
                                    "category": "Brake System",
                                    "type": "service_brakes",
                                    "status": "open",
                                    "defects": [
                                        {"title": "SECRET DEFECT TEXT", "notes": "SECRET NOTE", "severity": "major"}
                                    ],
                                }
                            ],
                        }
                    }
                )
            else:
                rows.append(
                    {
                        "inspection_report": {
                            "vehicle": {"number": "OTHER"},
                            "is_rejected": False,
                            "inspected_parts": [],
                        }
                    }
                )
        return {"inspection_reports": rows, "total": total}


def _row(result, truck):
    return next(row for row in result["classifications"] if row["truck_number"] == truck)


def test_paginates_complete_windows_and_returns_bounded_details():
    connector = FakeConnector(fault_total=150, report_total=125)
    result = maintenance_readiness_for_trucks(
        truck_numbers=["M2209", "M2210", "M2207", "M2201"],
        as_of_date=DAY,
        connector=connector,
    )
    assert result["fault_codes_window_complete"] is True
    assert result["inspection_reports_window_complete"] is True
    assert ("/v1/fault_codes", 2) in connector.calls
    assert ("/v2/inspection_reports", 2) in connector.calls

    m2209 = _row(result, "M2209")
    assert m2209["classification"] == "verify"
    assert m2209["open_fault_details"] == [
        {
            "status": "opened",
            "code": "SPN 3226",
            "code_label": "Outlet NOx",
            "code_description": "Outlet NOx sensor circuit",
            "first_observed_at": "2026-09-11T10:00:00Z",
            "last_observed_at": "2026-09-12T10:00:00Z",
            "occurrence_count": 2,
            "observation_count": 4,
            "fmi": 4,
            "fmi_description": "Voltage below normal",
            "severity_used_for_decision": False,
        }
    ]
    assert m2209["safety_classification_certified"] is False

    m2210 = _row(result, "M2210")
    assert m2210["classification"] == "not_suitable"
    rejected = m2210["inspection_issue_details"][0]
    assert rejected["is_rejected"] is True
    assert rejected["report_date"] == "2026-09-12"
    assert rejected["inspection_type"] == "pre_trip"

    m2207 = _row(result, "M2207")
    assert m2207["classification"] == "verify"
    detail = m2207["inspection_issue_details"][0]
    assert detail["part_name"] == "Brakes"
    assert detail["part_category"] == "Brake System"
    assert detail["part_type"] == "service_brakes"
    assert detail["part_status"] == "open"
    assert detail["defect_count"] == 1
    assert detail["safety_related_confirmed"] is False

    rendered = repr(result)
    assert "VIN-SECRET" not in rendered
    assert "SECRET DEFECT TEXT" not in rendered
    assert "SECRET NOTE" not in rendered
    assert "https://secret.example/signature" not in rendered
    assert "critical" not in rendered
    assert _row(result, "M2201")["classification"] == "clear"


def test_provider_failure_fails_to_verify():
    result = maintenance_readiness_for_trucks(
        truck_numbers=["M2201"], as_of_date=DAY, connector=FakeConnector(fail=True)
    )
    assert _row(result, "M2201")["classification"] == "verify"


def test_hard_cap_fails_to_verify():
    total = PAGE_SIZE * MAX_PAGES + 1
    result = maintenance_readiness_for_trucks(
        truck_numbers=["M2201"],
        as_of_date=DAY,
        connector=FakeConnector(fault_total=total, report_total=total),
    )
    row = _row(result, "M2201")
    assert row["classification"] == "verify"
    assert "fault_code_result_window_incomplete" in row["verification_reasons"]
    assert "inspection_result_window_incomplete" in row["verification_reasons"]


def test_details_are_truncated_without_changing_counts():
    class ManyOpenFaults(FakeConnector):
        def _request_json(self, endpoint: str, *, params: dict, operation: str):
            if endpoint == "/v1/fault_codes":
                rows = [
                    {"fault_code": {"status": "opened", "code": f"F{i}", "vehicle": {"number": "M2209"}}}
                    for i in range(MAX_DETAILS_PER_TRUCK + 2)
                ]
                return {"fault_codes": rows, "total": len(rows)}
            return {"inspection_reports": [], "total": 0}

    result = maintenance_readiness_for_trucks(
        truck_numbers=["M2209"], as_of_date=DAY, connector=ManyOpenFaults()
    )
    row = _row(result, "M2209")
    assert row["opened_fault_count"] == MAX_DETAILS_PER_TRUCK + 2
    assert len(row["open_fault_details"]) == MAX_DETAILS_PER_TRUCK
    assert row["fault_details_truncated"] is True
