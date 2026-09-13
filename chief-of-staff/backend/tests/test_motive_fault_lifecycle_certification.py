from datetime import date
from types import SimpleNamespace

from app.motive import fault_lifecycle_certification as mod


class FakeConnector:
    def _request_json(self, endpoint, *, params, operation):
        assert endpoint == "/v1/fault_codes"
        assert params["start_date"] == "2026-08-15"
        assert params["end_date"] == "2026-09-13"
        assert params["per_page"] == 100
        assert params["page_no"] == 1
        assert operation == "fault_lifecycle_certification"
        return {
            "total": 3,
            "fault_codes": [
                {
                    "fault_code": {
                        "id": "fc-1",
                        "status": "open",
                        "code": "97",
                        "fmi": 3,
                        "network_id": "engine",
                        "source": "ecm",
                        "source_address": 0,
                        "code_label": "water-in-fuel",
                        "first_observed_at": "2026-09-08T10:00:00Z",
                        "last_observed_at": "2026-09-09T10:00:00Z",
                        "vehicle": {"id": "vehicle-1", "number": "M2209"},
                    }
                },
                {
                    "fault_code": {
                        "id": "fc-2",
                        "status": "closed",
                        "code": "97",
                        "fmi": 3,
                        "network_id": "engine",
                        "source": "ecm",
                        "source_address": 0,
                        "code_label": "water-in-fuel",
                        "first_observed_at": "2026-09-01T10:00:00Z",
                        "last_observed_at": "2026-09-02T10:00:00Z",
                        "vehicle": {"id": "vehicle-1", "number": "M2209"},
                    }
                },
                {
                    "fault_code": {
                        "id": "fc-3",
                        "status": "open",
                        "code": "3226",
                        "fmi": 4,
                        "network_id": "engine",
                        "source": "ecm",
                        "source_address": 0,
                        "code_label": "outlet-nox",
                        "first_observed_at": "2026-09-09T11:00:00Z",
                        "last_observed_at": "2026-09-09T11:30:00Z",
                        "vehicle": {"id": "vehicle-1", "number": "M2209"},
                    }
                },
            ],
        }


def test_fault_lifecycle_certification_is_aggregate_only(monkeypatch):
    monkeypatch.setattr(mod, "resolve_scheduled_organization", lambda session: SimpleNamespace(id="org-mor"))
    result = mod.certify_fault_lifecycle_evidence(
        object(), certification_date=date(2026, 9, 13), connector=FakeConnector()
    )

    assert result["records_observed"] == 3
    assert result["status_counts"] == {"closed": 1, "open": 2}
    assert result["open_records_found"] is True
    assert result["closed_records_found"] is True
    assert result["provider_record_id_present_all_records"] is True
    assert result["provider_record_id_unique_within_window"] is True
    assert result["same_provider_id_observed_across_statuses"] is False
    assert result["identity_field_evidence"]["code"]["values_seen_with_multiple_statuses"] == 1
    assert result["identity_field_evidence"]["vehicle.id"]["values_seen_with_multiple_statuses"] == 1
    assert result["first_last_order_invalid_count"] == 0
    assert result["stable_identity_over_time_certified"] is False
    assert result["open_to_closed_transition_certified"] is False
    assert result["durable_fault_memory_enabled"] is False
    assert result["provider_writes_performed"] is False
    assert result["database_writes_performed"] is False

    rendered = repr(result)
    assert "M2209" not in rendered
    assert "fc-1" not in rendered
    assert "3226" not in rendered
