import base64
from urllib.parse import parse_qs, urlsplit

import pytest

from app.github_engine.client import GitHubClient, GitHubEngineError


def make_client(monkeypatch):
    monkeypatch.setenv("POLARIS_GITHUB_TOKEN", "test")
    monkeypatch.setenv(
        "POLARIS_GITHUB_REPOSITORY",
        GitHubClient.REPOSITORY,
    )
    return GitHubClient()


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


def test_unsafe_path_rejected(monkeypatch):
    client = make_client(monkeypatch)
    with pytest.raises(GitHubEngineError, match="Unsafe"):
        client.read_file("../secret.txt")


def test_repository_tree_uses_requested_ref(monkeypatch):
    client = make_client(monkeypatch)
    calls = []

    def fake_request(method, path, payload=None):
        calls.append((method, path, payload))
        return {"sha": "abc", "tree": [], "truncated": False}

    monkeypatch.setattr(client, "request", fake_request)
    result = client.repository_tree("feature/test", recursive=True)

    assert result["sha"] == "abc"
    assert calls == [
        (
            "GET",
            "/repos/ThePolarisLab/Polaris-Lab/git/trees/"
            "feature%2Ftest?recursive=1",
            None,
        )
    ]


def test_read_file_decodes_utf8_content(monkeypatch):
    client = make_client(monkeypatch)
    encoded = base64.b64encode(b"hello Polaris").decode()

    def fake_request(method, path, payload=None):
        return {
            "type": "file",
            "path": "README.md",
            "name": "README.md",
            "sha": "abc",
            "size": 13,
            "encoding": "base64",
            "content": encoded,
            "html_url": "https://example.test/README.md",
        }

    monkeypatch.setattr(client, "request", fake_request)
    result = client.read_file("README.md", "main")

    assert result["content"] == "hello Polaris"
    assert result["ref"] == "main"


def test_search_code_scopes_query_to_allowlisted_repository(monkeypatch):
    client = make_client(monkeypatch)
    calls = []

    def fake_request(method, path, payload=None):
        calls.append(path)
        return {"total_count": 0, "items": []}

    monkeypatch.setattr(client, "request", fake_request)
    client.search_code("GitHubClient", per_page=10)

    assert calls
    query = parse_qs(urlsplit(calls[0]).query)
    assert query["q"] == [
        "GitHubClient repo:ThePolarisLab/Polaris-Lab"
    ]
    assert query["per_page"] == ["10"]


def test_commit_limit_is_capped(monkeypatch):
    client = make_client(monkeypatch)
    calls = []

    def fake_request(method, path, payload=None):
        calls.append(path)
        return []

    monkeypatch.setattr(client, "request", fake_request)
    client.commits(per_page=1000)

    assert "per_page=100" in calls[0]
