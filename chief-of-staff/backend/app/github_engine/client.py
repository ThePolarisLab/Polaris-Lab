import base64
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class GitHubEngineError(RuntimeError):
    pass


class GitHubClient:
    REPOSITORY = "ThePolarisLab/Polaris-Lab"
    MAX_FILE_BYTES = 1_000_000

    def __init__(self):
        self.token = os.getenv("POLARIS_GITHUB_TOKEN", "").strip()
        self.repository = os.getenv(
            "POLARIS_GITHUB_REPOSITORY",
            self.REPOSITORY,
        ).strip()
        self.write_enabled = (
            os.getenv("POLARIS_GITHUB_WRITE_ENABLED", "false").lower()
            == "true"
        )
        if not self.token:
            raise GitHubEngineError(
                "POLARIS_GITHUB_TOKEN is not configured."
            )
        if self.repository != self.REPOSITORY:
            raise GitHubEngineError(
                "Repository is not on the PGE-001 allowlist."
            )

    def request(self, method, path, payload=None):
        body = (
            json.dumps(payload).encode()
            if payload is not None
            else None
        )
        req = Request(
            f"https://api.github.com{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Polaris-GitHub-Engine/0.2",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(req, timeout=30) as response:
                raw = response.read().decode()
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            details = exc.read().decode(errors="replace")
            raise GitHubEngineError(
                f"GitHub API returned {exc.code}: {details}"
            ) from exc
        except URLError as exc:
            raise GitHubEngineError(
                f"GitHub connection failed: {exc.reason}"
            ) from exc

    @staticmethod
    def normalize_path(path):
        clean_path = path.strip().strip("/")
        if ".." in clean_path.split("/"):
            raise GitHubEngineError("Unsafe repository path.")
        return clean_path

    def require_write(self):
        if not self.write_enabled:
            raise GitHubEngineError(
                "Writes are disabled. Set "
                "POLARIS_GITHUB_WRITE_ENABLED=true after review."
            )

    def repository_info(self):
        return self.request("GET", f"/repos/{self.repository}")

    def branches(self):
        return self.request(
            "GET",
            f"/repos/{self.repository}/branches?per_page=100",
        )

    def repository_tree(self, ref="main", recursive=True):
        encoded_ref = quote(ref, safe="")
        recursive_value = "1" if recursive else "0"
        return self.request(
            "GET",
            f"/repos/{self.repository}/git/trees/{encoded_ref}"
            f"?recursive={recursive_value}",
        )

    def read_file(self, path, ref="main"):
        clean_path = self.normalize_path(path)
        if not clean_path:
            raise GitHubEngineError("A file path is required.")

        encoded_path = quote(clean_path, safe="/")
        query = urlencode({"ref": ref})
        result = self.request(
            "GET",
            f"/repos/{self.repository}/contents/{encoded_path}?{query}",
        )

        if result.get("type") != "file":
            raise GitHubEngineError(
                f"Repository path is not a file: {clean_path}"
            )

        size = int(result.get("size", 0))
        if size > self.MAX_FILE_BYTES:
            raise GitHubEngineError(
                f"File exceeds the {self.MAX_FILE_BYTES}-byte read limit."
            )

        encoding = result.get("encoding")
        encoded_content = result.get("content", "")
        if encoding != "base64":
            raise GitHubEngineError(
                "GitHub returned an unsupported file encoding."
            )

        try:
            content = base64.b64decode(encoded_content).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise GitHubEngineError(
                "File is not valid UTF-8 text."
            ) from exc

        return {
            "path": result.get("path", clean_path),
            "name": result.get("name"),
            "sha": result.get("sha"),
            "size": size,
            "ref": ref,
            "content": content,
            "html_url": result.get("html_url"),
        }

    def search_code(self, query, ref=None, per_page=30):
        clean_query = query.strip()
        if not clean_query:
            raise GitHubEngineError("A code search query is required.")

        search_query = f"{clean_query} repo:{self.repository}"
        if ref:
            search_query += f" ref:{ref}"

        params = urlencode(
            {
                "q": search_query,
                "per_page": min(max(per_page, 1), 100),
            }
        )
        return self.request("GET", f"/search/code?{params}")

    def commits(self, ref="main", path=None, per_page=30):
        params = {
            "sha": ref,
            "per_page": min(max(per_page, 1), 100),
        }
        if path:
            params["path"] = self.normalize_path(path)
        return self.request(
            "GET",
            f"/repos/{self.repository}/commits?{urlencode(params)}",
        )

    def create_branch(self, branch_name, base_branch):
        self.require_write()
        base = self.request(
            "GET",
            f"/repos/{self.repository}/git/ref/heads/{base_branch}",
        )
        return self.request(
            "POST",
            f"/repos/{self.repository}/git/refs",
            {
                "ref": f"refs/heads/{branch_name}",
                "sha": base["object"]["sha"],
            },
        )

    def write_file(
        self,
        path,
        content,
        branch,
        commit_message,
        existing_sha=None,
    ):
        self.require_write()
        clean_path = self.normalize_path(path)
        if not clean_path:
            raise GitHubEngineError("A file path is required.")
        payload = {
            "message": commit_message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        if existing_sha:
            payload["sha"] = existing_sha
        encoded_path = quote(clean_path, safe="/")
        return self.request(
            "PUT",
            f"/repos/{self.repository}/contents/{encoded_path}",
            payload,
        )

    def create_pull_request(
        self,
        title,
        body,
        head_branch,
        base_branch,
        draft=True,
    ):
        self.require_write()
        return self.request(
            "POST",
            f"/repos/{self.repository}/pulls",
            {
                "title": title,
                "body": body,
                "head": head_branch,
                "base": base_branch,
                "draft": draft,
            },
        )
