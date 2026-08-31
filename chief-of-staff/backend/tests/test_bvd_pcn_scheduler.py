from __future__ import annotations

from types import SimpleNamespace

from app.fuel import scheduler


def test_scheduler_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv(scheduler.SCHEDULED_IMPORT_ENABLED_ENV_VAR, raising=False)

    result = scheduler.run_scheduled_bvd_pcn_import(object())

    assert result["status"] == "disabled"
    assert result["scheduler_enabled"] is False
    assert result["currencies"] == {}
    assert result["outlook_read_only"] is True
    assert result["supplier_api_called"] is False
    assert result["secrets_exposed"] is False


def test_scheduler_imports_both_currencies_with_tenant_scope(monkeypatch) -> None:
    monkeypatch.setenv(scheduler.SCHEDULED_IMPORT_ENABLED_ENV_VAR, "true")
    organization = SimpleNamespace(
        id="org-1",
        slug="mor",
        legal_name="MOR LOGISTICS MANITOBA LIMITED",
        display_name="MOR Logistics",
    )
    monkeypatch.setattr(scheduler, "resolve_scheduled_organization", lambda session: organization)

    credential_store_calls: list[str] = []
    connector_calls: list[object] = []
    import_calls: list[tuple[str, str, str]] = []

    def fake_store(organization_id: str):
        credential_store_calls.append(organization_id)
        return SimpleNamespace(organization_id=organization_id)

    def fake_connector(*, credential_store):
        connector_calls.append(credential_store)
        return SimpleNamespace(read_only=True)

    def fake_import(session, organization_id, *, connector, expected_company_name, currency):
        import_calls.append((organization_id, expected_company_name, currency))
        return {
            "status": "idempotent_replay" if currency == "CAD" else "import_success",
            "source_found": True,
            "replayed": currency == "CAD",
            "effective_start": "2026-08-31",
            "effective_end": "2026-08-31",
            "records_read": 92 if currency == "CAD" else 605,
            "records_inserted": 92 if currency == "CAD" else 605,
            "error_category": None,
        }

    monkeypatch.setattr(scheduler, "OutlookCredentialStore", fake_store)
    monkeypatch.setattr(scheduler, "OutlookConnector", fake_connector)
    monkeypatch.setattr(scheduler, "import_latest_bvd_pcn_outlook", fake_import)

    result = scheduler.run_scheduled_bvd_pcn_import(object())

    assert credential_store_calls == ["org-1"]
    assert len(connector_calls) == 1
    assert import_calls == [
        ("org-1", "MOR LOGISTICS MANITOBA LIMITED", "CAD"),
        ("org-1", "MOR LOGISTICS MANITOBA LIMITED", "USD"),
    ]
    assert result["status"] == "executed"
    assert result["tenant_scope_validated"] is True
    assert result["currencies"]["CAD"]["status"] == "idempotent_replay"
    assert result["currencies"]["USD"]["records_read"] == 605
    assert result["supplier_api_called"] is False
    assert result["secrets_exposed"] is False


def test_scheduler_treats_no_source_as_safe_noop(monkeypatch) -> None:
    monkeypatch.setenv(scheduler.SCHEDULED_IMPORT_ENABLED_ENV_VAR, "true")
    organization = SimpleNamespace(
        id="org-1",
        slug="mor",
        legal_name="MOR LOGISTICS MANITOBA LIMITED",
        display_name="MOR Logistics",
    )
    monkeypatch.setattr(scheduler, "resolve_scheduled_organization", lambda session: organization)
    monkeypatch.setattr(scheduler, "OutlookCredentialStore", lambda organization_id: object())
    monkeypatch.setattr(scheduler, "OutlookConnector", lambda *, credential_store: object())
    monkeypatch.setattr(
        scheduler,
        "import_latest_bvd_pcn_outlook",
        lambda *args, currency, **kwargs: {
            "status": "no_source_found",
            "source_found": False,
            "replayed": False,
            "records_read": 0,
            "records_inserted": 0,
        },
    )

    result = scheduler.run_scheduled_bvd_pcn_import(object())

    assert result["status"] == "no_source_found"
    assert result["currencies"]["CAD"]["source_found"] is False
    assert result["currencies"]["USD"]["source_found"] is False


def test_scheduler_surfaces_sanitized_currency_failure(monkeypatch) -> None:
    monkeypatch.setenv(scheduler.SCHEDULED_IMPORT_ENABLED_ENV_VAR, "true")
    organization = SimpleNamespace(
        id="org-1",
        slug="mor",
        legal_name="MOR LOGISTICS MANITOBA LIMITED",
        display_name="MOR Logistics",
    )
    monkeypatch.setattr(scheduler, "resolve_scheduled_organization", lambda session: organization)
    monkeypatch.setattr(scheduler, "OutlookCredentialStore", lambda organization_id: object())
    monkeypatch.setattr(scheduler, "OutlookConnector", lambda *, credential_store: object())

    def fake_import(*args, currency, **kwargs):
        if currency == "USD":
            return {
                "status": "source_contract_error",
                "source_found": True,
                "replayed": False,
                "records_read": 0,
                "records_inserted": 0,
                "error_category": None,
            }
        return {
            "status": "idempotent_replay",
            "source_found": True,
            "replayed": True,
            "effective_start": "2026-08-31",
            "effective_end": "2026-09-01",
            "records_read": 92,
            "records_inserted": 92,
            "error_category": None,
        }

    monkeypatch.setattr(scheduler, "import_latest_bvd_pcn_outlook", fake_import)

    result = scheduler.run_scheduled_bvd_pcn_import(object())

    assert result["status"] == "failed"
    assert result["currencies"]["USD"]["status"] == "source_contract_error"
    assert "message_id" not in str(result)
    assert "attachment" not in str(result)
    assert result["secrets_exposed"] is False
