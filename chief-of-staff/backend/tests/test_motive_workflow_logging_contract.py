from pathlib import Path


def test_motive_workflow_logs_only_sanitized_production_result_fields():
    repo_root = Path(__file__).resolve().parents[3]
    workflow = (repo_root / ".github" / "workflows" / "motive-vehicle-utilization-daily.yml").read_text(
        encoding="utf-8"
    )

    expected_fields = (
        "status",
        "horizon_days",
        "selected_vehicle_count",
        "windows_attempted",
        "windows_completed",
        "windows_failed",
        "provider_calls_attempted",
        "provider_calls_completed",
        "rollups_returned",
        "missing_requested_vehicle_count",
        "records_inserted",
        "records_unchanged",
        "records_updated",
        "reconciled_fields_count",
        "checkpoint_advanced",
        "sync_history_written",
        "secrets_exposed",
    )

    assert 'production_result = payload.get("production_result")' in workflow
    assert "allowed_production_fields = (" in workflow
    assert 'print("Production result: " + json.dumps(sanitized_production_result, sort_keys=True))' in workflow
    for field in expected_fields:
        assert f'"{field}"' in workflow

    # Keep provider payloads, identities, and credential-bearing fields out of logs.
    forbidden_fields = (
        "provider_vehicle_id",
        "unit_number",
        "vin",
        "license_plate",
        "access_token",
        "refresh_token",
        "authorization",
        "failed_units",
    )
    for field in forbidden_fields:
        assert f'"{field}"' not in workflow
