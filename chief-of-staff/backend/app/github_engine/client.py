import base64, json, os
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

class GitHubEngineError(RuntimeError):
    pass

class GitHubClient:
    REPOSITORY = "ThePolarisLab/Polaris-Lab"

    def __init__(self):
        self.token = os.getenv("POLARIS_GITHUB_TOKEN", "").strip()
        self.repository = os.getenv("POLARIS_GITHUB_REPOSITORY", self.REPOSITORY).strip()
        self.write_enabled = os.getenv("POLARIS_GITHUB_WRITE_ENABLED", "false").lower() == "true"
        if not self.token:
            raise GitHubEngineError("POLARIS_GITHUB_TOKEN is not configured.")
        if self.repository != self.REPOSITORY:
            raise GitHubEngineError("Repository is not on the PGE-001 allowlist.")

    def request(self, method, path, payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        req = Request(
            f"https://api.github.com{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Polaris-GitHub-Engine/0.1",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(req, timeout=30) as response:
                raw = response.read().decode()
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            details = exc.read().decode(errors="replace")
            raise GitHubEngineError(f"GitHub API returned {exc.code}: {details}") from exc
        except URLError as exc:
            raise GitHubEngineError(f"GitHub connection failed: {exc.reason}") from exc

    def require_write(self):
        if not self.write_enabled:
            raise GitHubEngineError("Writes are disabled. Set POLARIS_GITHUB_WRITE_ENABLED=true after review.")

    def repository_info(self):
        return self.request("GET", f"/repos/{self.repository}")

    def branches(self):
        return self.request("GET", f"/repos/{self.repository}/branches?per_page=100")

    def create_branch(self, branch_name, base_branch):
        self.require_write()
        base = self.request("GET", f"/repos/{self.repository}/git/ref/heads/{base_branch}")
        return self.request("POST", f"/repos/{self.repository}/git/refs", {
            "ref": f"refs/heads/{branch_name}",
            "sha": base["object"]["sha"],
        })

    def write_file(self, path, content, branch, commit_message, existing_sha=None):
        self.require_write()
        path = path.strip().lstrip("/")
        if ".." in path.split("/"):
            raise GitHubEngineError("Unsafe repository path.")
        payload = {
            "message": commit_message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        if existing_sha:
            payload["sha"] = existing_sha
        return self.request("PUT", f"/repos/{self.repository}/contents/{path}", payload)

    def create_pull_request(self, title, body, head_branch, base_branch, draft=True):
        self.require_write()
        return self.request("POST", f"/repos/{self.repository}/pulls", {
            "title": title,
            "body": body,
            "head": head_branch,
            "base": base_branch,
            "draft": draft,
        })
