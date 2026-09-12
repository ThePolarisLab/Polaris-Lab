from __future__ import annotations

from datetime import date

from app.motive.maintenance_readiness import MAX_PAGES, PAGE_SIZE, maintenance_readiness_for_trucks

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
            rows = [{"fault_code": {"status": "opened" if i == 0 else "closed", "vehicle": {"number": "M2209" if i == 0 else "OTHER"}}} for i in range(start, stop)]
            return {"fault_codes": rows, "total": total}
        rows = []
        for i in range(start, stop):
            if i == 0:
                rows.append({"inspection_report": {"vehicle": {"number": "M2210"}, "is_rejected": True, "inspected_parts": []}})
            elif i == 1:
                rows.append({"inspection_report": {"vehicle": {"number": "M2207"}, "is_rejected": False, "inspected_parts": [{"status": "open"}]}})
            else:
                rows.append({"inspection_report": {"vehicle": {"number": "OTHER"}, "is_rejected": False, "inspected_parts": []}})
        return {"inspection_reports": rows, "total": total}


def _row(result, truck):
    return next(row for row in result["classifications"] if row["truck_number"] == truck)


def test_paginates_complete_windows():
    connector = FakeConnector(fault_total=150, report_total=125)
    result = maintenance_readiness_for_trucks(truck_numbers=["M2209", "M2210", "M2207", "M2201"], as_of_date=DAY, connector=connector)
    assert result["fault_codes_window_complete"] is True
    assert result["inspection_reports_window_complete"] is True
    assert ("/v1/fault_codes", 2) in connector.calls
    assert ("/v2/inspection_reports", 2) in connector.calls
    assert _row(result, "M2209")["classification"] == "verify"
    assert _row(result, "M2210")["classification"] == "not_suitable"
    assert _row(result, "M2207")["classification"] == "verify"
    assert _row(result, "M2201")["classification"] == "clear"


def test_provider_failure_fails_to_verify():
    result = maintenance_readiness_for_trucks(truck_numbers=["M2201"], as_of_date=DAY, connector=FakeConnector(fail=True))
    assert _row(result, "M2201")["classification"] == "verify"


def test_hard_cap_fails_to_verify():
    total = PAGE_SIZE * MAX_PAGES + 1
    result = maintenance_readiness_for_trucks(truck_numbers=["M2201"], as_of_date=DAY, connector=FakeConnector(fault_total=total, report_total=total))
    row = _row(result, "M2201")
    assert row["classification"] == "verify"
    assert "fault_code_result_window_incomplete" in row["verification_reasons"]
    assert "inspection_result_window_incomplete" in row["verification_reasons"]
