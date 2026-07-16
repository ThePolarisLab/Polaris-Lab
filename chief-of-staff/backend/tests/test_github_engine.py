import pytest
from app.github_engine.client import GitHubClient, GitHubEngineError

def test_write_disabled(monkeypatch):
    monkeypatch.setenv("POLARIS_GITHUB_TOKEN", "test")
    monkeypatch.setenv("POLARIS_GITHUB_WRITE_ENABLED", "false")
    client = GitHubClient()
    with pytest.raises(GitHubEngineError, match="Writes are disabled"):
        client.create_branch("test", "main")

def test_repository_allowlist(monkeypatch):
    monkeypatch.setenv("POLARIS_GITHUB_TOKEN", "test")
    monkeypatch.setenv("POLARIS_GITHUB_REPOSITORY", "other/repo")
    with pytest.raises(GitHubEngineError, match="allowlist"):
        GitHubClient()
