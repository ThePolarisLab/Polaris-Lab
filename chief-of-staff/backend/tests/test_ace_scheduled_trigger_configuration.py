from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_render_blueprint_removes_paid_cron_and_keeps_backend_trigger_config():
    render_text = (REPO_ROOT / "render.yaml").read_text()

    assert "type: cron" not in render_text
    assert "name: polaris-executive-api" in render_text
    assert "type: web" in render_text
    assert "python -m app.jobs.ace_daily_import" not in render_text
    assert "- key: POLARIS_ACE_DAILY_IMPORT_ORGANIZATION_SLUG\n        sync: false" in render_text
    assert "- key: POLARIS_ACE_CRON_TRIGGER_SECRET\n        sync: false" in render_text
    assert "POLARIS_ACE_CRON_TRIGGER_SECRET\n        value:" not in render_text
    assert "openid profile email offline_access https://graph.microsoft.com/Mail.Read" in render_text


def test_github_workflow_uses_only_narrow_trigger_secret_and_safe_schedule():
    workflow_text = (REPO_ROOT / ".github" / "workflows" / "ace-daily-feed.yml").read_text()
    assert 'cron: "40 10-14 * * *"' in workflow_text
    assert "group: ace-daily-feed-production" in workflow_text
    assert "POLARIS_ACE_CRON_TRIGGER_SECRET" in workflow_text
    assert "DATABASE_URL" not in workflow_text
    assert "POLARIS_OUTLOOK_CLIENT_SECRET" not in workflow_text
    assert "POLARIS_OUTLOOK_TOKEN_ENCRYPTION_KEY" not in workflow_text
    assert "POLARIS_ACE_DAILY_IMPORT_ORGANIZATION_SLUG" not in workflow_text
    assert "Mail.ReadWrite" not in workflow_text
    assert "Mail.Send" not in workflow_text
    assert "--max-time 240" in workflow_text
    assert "sleep 60" in workflow_text
    assert "/api/v1/internal/ace/daily-feed/run" in workflow_text
