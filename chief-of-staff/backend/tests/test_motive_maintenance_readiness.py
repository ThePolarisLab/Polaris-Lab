from __future__ import annotations

from datetime import date

from app.motive.maintenance_readiness import maintenance_readiness_for_trucks

DAY = date(2026, 9, 12)


class FakeConnector:
    def __init__(self, *, fail_faults=False, fail_reports=False, fault_total=2, report_total=3):
        self.fail_faults = fail_faults
        self.fail_reports = fail_reports
        self.fault_total = fault_total
        self.report_total = report_total

    def _request_json(self, endpoint: str, *, params: dict, operation: str):
        from app.connectors.motive import MotiveConnectorError
        if endpoint == "/v1/fault_codes":
            if self.fail_faults:
                raise MotiveConnectorError("unavailable", http_status=503)
            return {
                "fault_codes": [
                    {"fault_code": {"status": "opened", "vehicle": {"number": "M2209"}}},
                    {"fault_code": {"status": "closed", "vehicle": {"number": "M2210"}}},
                ],
                "total": self.fault_total,
            }
        if endpoint == "/v2/inspection_reports":
            if self.fail_reports:
                raise MotiveConnectorError("unavailable", http_status=503)
            return {
                "inspection_reports": [
                    {"inspection_report": {"vehicle": {"number": "M2210"}, "is_rejected": True, "inspected_parts": []}},
                    {"inspection_report": {"vehicle": {"number": "M2214"}, "is_rejected": False,
                     "inspected_parts": [{"status": "open", "type": "major"}]}},
                    {"inspection_report": {"vehicle": {"number": "M2207"}, "is_rejected": False,
                     "inspected_parts": [{"status": "open", "type": "minor"}]}},
                ],
                "total": self.report_total,
            }
        raise AssertionError(endpoint)


def _by_truck(result):
    return {row["truck_number"]: row for row in result["classifications"]}


def test_maintenance_readiness_is_conservative_and_read_only():
    result = maintenance_readiness_for_trucks(
        truck_numbers=["M2209", "M2210", "M2214", "M2207", "M2201"],
        as_of_date=DAY,
        connector=FakeConnector(),
    )
    rows = _by_truck(result)
    assert rows["M2209"]["classification"] == "verify"
    assert rows["M2209"]["verification_reasons"] == ["opened_fault_code_present"]
    assert rows["M2210"]["classification"] == "not_suitable"
    assert rows["M2210"]["hard_blockers"] == ["inspection_report_rejected"]
    assert rows["M2214"]["classification"] == "verify"
    assert rows["M2207"]["classification"] == "verify"
    assert rows["M2201"]["classification"] == "clear"
    assert result["fault_codes_window_complete"] is True
    assert result["inspection_reports_window_complete"] is True
    assert result["provider_writes_performed"] is False
    assert result["dispatch_mutation_performed"] is False
    assert result["autonomous_assignment_performed"] is False


def test_provider_failure_fails_to_verify_not_clear():
    result = maintenance_readiness_for_trucks(
        truck_numbers=["M2201"], as_of_date=DAY,
        connector=FakeConnector(fail_faults=True, fail_reports=True),
    )
    row = result["classifications"][0]
    assert row["classification"] == "verify"
    assert "fault_code_data_unavailable" in row["verification_reasons"]
    assert "inspection_data_unavailable" in row["verification_reasons"]


def test_partial_provider_window_fails_to_verify_not_clear():
    result = maintenance_readiness_for_trucks(
        truck_numbers=["M2201"], as_of_date=DAY,
        connector=FakeConnector(fault_total=101, report_total=101),
    )
    row = result["classifications"][0]
    assert row["classification"] == "verify"
    assert "fault_code_result_window_incomplete" in row["verification_reasons"]
    assert "inspection_result_window_incomplete" in row["verification_reasons"]
