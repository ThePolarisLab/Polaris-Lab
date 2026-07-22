from app.connectors.github import GitHubConnector
from app.connectors.models import ConnectorStatus
from app.events.bus import EventBus
from app.github_engine.client import GitHubEngineError


class FakeGitHubClient:
    def repository_info(self):
        return {
            "full_name": "ThePolarisLab/Polaris-Lab",
            "default_branch": "main",
            "private": True,
        }

    def commits(self, ref="main", path=None, per_page=30):
        return [
            {
                "sha": "abc123",
                "html_url": "https://example.test/commit/abc123",
                "commit": {
                    "message": "feat: first commit\n\nDetails",
                    "author": {
                        "name": "Polaris Builder",
                        "date": "2026-07-22T00:00:00Z",
                    },
                },
            },
            {
                "sha": "def456",
                "html_url": "https://example.test/commit/def456",
                "commit": {
                    "message": "test: second commit",
                    "author": {
                        "name": "Polaris Builder",
                        "date": "2026-07-22T00:01:00Z",
                    },
                },
            },
        ]


class BrokenGitHubClient:
    def repository_info(self):
        raise GitHubEngineError("GitHub API returned 503")


def test_github_connector_reports_health_and_capabilities():
    connector = GitHubConnector(client_factory=FakeGitHubClient, bus=EventBus())

    health = connector.health()

    assert health.status == ConnectorStatus.HEALTHY
    assert health.details["repository"] == "ThePolarisLab/Polaris-Lab"
    assert "repository.commits" in connector.discover()


def test_github_connector_sync_publishes_commit_events():
    bus = EventBus(history_size=10)
    connector = GitHubConnector(client_factory=FakeGitHubClient, bus=bus)

    result = connector.sync()
    events = bus.recent(limit=10)

    assert result.success is True
    assert result.records_read == 2
    assert result.events_published == 2
    assert [event.entity for event in events] == ["def456", "abc123"]
    assert all(event.event_type == "github.commit.observed" for event in events)


def test_github_connector_isolates_client_errors():
    connector = GitHubConnector(client_factory=BrokenGitHubClient, bus=EventBus())

    health = connector.health()
    result = connector.sync()

    assert health.status == ConnectorStatus.DEGRADED
    assert result.success is False
    assert result.events_published == 0
    assert result.errors == ["GitHub API returned 503"]
