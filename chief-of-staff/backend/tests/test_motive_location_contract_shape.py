"""Structural diagnostics for Motive v3 vehicle-location envelopes."""
import pytest

from app.motive import location_sync as sync


@pytest.mark.parametrize(
    "payload, expected_reason",
    [
        ({"vehicles": []}, "location_contract_unavailable"),
        (["sample"], "unexpected_unavailable"),
        ({"sample": True}, "unexpected_unavailable"),
        ({"vehicles": {"sample": True}}, "unexpected_unavailable"),
        ({"vehicles": [{}, {}]}, "unexpected_unavailable"),
    ],
)
def test_only_zero_rows_use_existing_contract_unavailable_bucket(payload, expected_reason):
    with pytest.raises(sync.LocationSyncError) as caught:
        sync._location(payload, "101", "2218")
    assert sync._unavailable_reason(caught.value) == expected_reason
