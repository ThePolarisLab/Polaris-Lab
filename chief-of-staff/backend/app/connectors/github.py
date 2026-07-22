"""Production GitHub connector built on the Polaris Connector SDK."""

from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from app.connectors.base import BaseConnector
from app.connectors.models import ConnectorHealth, ConnectorStatus, SyncResult
from app.events.bus import EventBus, event_bus
from app.events.models import ConnectorEvent
from app.github_engine.client import GitHubClient, GitHubEngineError


class GitHubConnector(BaseConnector):
    """Read repository activity and publish normalized Polaris events."""

    def __init__(
        self,
        *,
        client_factory: Callable[[], GitHubClient] = GitHubClient,
        bus: EventBus = event_bus,
    ) -> None:
        super().__init__(name="github")
        self._client_factory = client_factory
        self._bus = bus
        self._client: GitHubClient | None = None

    def validate_configuration(self) -> None:
        self._client = self._client_factory()

    def authenticate(self) -> None:
        self._get_client().repository_info()

    def health(self) -> ConnectorHealth:
        started = datetime.now(timezone.utc)
        try:
            repository = self._get_client().repository_info()
        except GitHubEngineError as exc:
            status = (
                ConnectorStatus.CONFIGURATION_ERROR
                if "not configured" in str(exc).lower()
                else ConnectorStatus.DEGRADED
            )
            return ConnectorHealth(
                name=self.name,
                status=status,
                message=str(exc),
            )

        latency_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
        return ConnectorHealth(
            name=self.name,
            status=ConnectorStatus.HEALTHY,
            latency_ms=round(latency_ms, 2),
            message="GitHub repository is reachable.",
            details={
                "repository": repository.get("full_name"),
                "default_branch": repository.get("default_branch"),
                "private": repository.get("private"),
            },
        )

    def discover(self) -> Sequence[str]:
        return (
            "repository.metadata",
            "repository.branches",
            "repository.commits",
            "repository.events",
        )

    def sync(self) -> SyncResult:
        started_at = datetime.now(timezone.utc)
        records_read = 0
        events_published = 0
        errors: list[str] = []

        try:
            client = self._get_client()
            repository = client.repository_info()
            default_branch = repository.get("default_branch", "main")
            commits = client.commits(default_branch, per_page=30)
            records_read = len(commits)

            for commit in reversed(commits):
                commit_data = commit.get("commit", {})
                author = commit_data.get("author", {})
                event = ConnectorEvent(
                    connector=self.name,
                    event_type="github.commit.observed",
                    entity=commit.get("sha"),
                    payload={
                        "repository": repository.get("full_name"),
                        "branch": default_branch,
                        "sha": commit.get("sha"),
                        "message": commit_data.get("message", "").splitlines()[0],
                        "author": author.get("name"),
                        "authored_at": author.get("date"),
                        "html_url": commit.get("html_url"),
                    },
                )
                self._bus.publish(event)
                events_published += 1
        except GitHubEngineError as exc:
            errors.append(str(exc))

        completed_at = datetime.now(timezone.utc)
        return SyncResult(
            connector=self.name,
            started_at=started_at,
            completed_at=completed_at,
            records_read=records_read,
            records_written=0,
            events_published=events_published,
            success=not errors,
            errors=errors,
        )

    def _get_client(self) -> GitHubClient:
        if self._client is None:
            self.validate_configuration()
        assert self._client is not None
        return self._client
