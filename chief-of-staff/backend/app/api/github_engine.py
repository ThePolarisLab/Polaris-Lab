from fastapi import APIRouter, HTTPException, Query

from app.github_engine.client import GitHubClient, GitHubEngineError
from app.github_engine.schemas import (
    BranchCreateRequest,
    FileWriteRequest,
    GitHubOperationResult,
    PullRequestCreateRequest,
)


router = APIRouter(
    prefix="/api/v1/github",
    tags=["Polaris GitHub Engine"],
)


def run(operation):
    try:
        return operation()
    except GitHubEngineError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/status", response_model=GitHubOperationResult)
def status():
    def op():
        client = GitHubClient()
        repo = client.repository_info()
        return GitHubOperationResult(
            success=True,
            message="GitHub Engine connected.",
            data={
                "repository": repo["full_name"],
                "default_branch": repo["default_branch"],
                "private": repo["private"],
                "write_enabled": client.write_enabled,
                "permissions": repo.get("permissions"),
            },
        )

    return run(op)


@router.get("/branches", response_model=GitHubOperationResult)
def branches():
    return run(
        lambda: GitHubOperationResult(
            success=True,
            message="Branches retrieved.",
            data=[
                {
                    "name": branch["name"],
                    "sha": branch["commit"]["sha"],
                    "protected": branch.get("protected", False),
                }
                for branch in GitHubClient().branches()
            ],
        )
    )


@router.get("/repository", response_model=GitHubOperationResult)
def repository():
    def op():
        repo = GitHubClient().repository_info()
        return GitHubOperationResult(
            success=True,
            message="Repository metadata retrieved.",
            data={
                "full_name": repo.get("full_name"),
                "description": repo.get("description"),
                "default_branch": repo.get("default_branch"),
                "private": repo.get("private"),
                "language": repo.get("language"),
                "size": repo.get("size"),
                "updated_at": repo.get("updated_at"),
                "html_url": repo.get("html_url"),
            },
        )

    return run(op)


@router.get("/tree", response_model=GitHubOperationResult)
def repository_tree(
    ref: str = Query(default="main", min_length=1, max_length=200),
    recursive: bool = Query(default=True),
):
    def op():
        tree = GitHubClient().repository_tree(ref, recursive)
        entries = [
            {
                "path": item.get("path"),
                "type": item.get("type"),
                "mode": item.get("mode"),
                "sha": item.get("sha"),
                "size": item.get("size"),
            }
            for item in tree.get("tree", [])
        ]
        return GitHubOperationResult(
            success=True,
            message=f"Repository tree retrieved for {ref}.",
            data={
                "sha": tree.get("sha"),
                "truncated": tree.get("truncated", False),
                "entries": entries,
            },
        )

    return run(op)


@router.get("/files/read", response_model=GitHubOperationResult)
def read_file(
    path: str = Query(min_length=1, max_length=1000),
    ref: str = Query(default="main", min_length=1, max_length=200),
):
    return run(
        lambda: GitHubOperationResult(
            success=True,
            message=f"Read {path}.",
            data=GitHubClient().read_file(path, ref),
        )
    )


@router.get("/search", response_model=GitHubOperationResult)
def search_code(
    q: str = Query(min_length=1, max_length=300),
    ref: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=30, ge=1, le=100),
):
    def op():
        result = GitHubClient().search_code(q, ref, limit)
        items = [
            {
                "name": item.get("name"),
                "path": item.get("path"),
                "sha": item.get("sha"),
                "html_url": item.get("html_url"),
            }
            for item in result.get("items", [])
        ]
        return GitHubOperationResult(
            success=True,
            message=f"Found {result.get('total_count', 0)} matches.",
            data={
                "total_count": result.get("total_count", 0),
                "incomplete_results": result.get(
                    "incomplete_results", False
                ),
                "items": items,
            },
        )

    return run(op)


@router.get("/commits", response_model=GitHubOperationResult)
def commits(
    ref: str = Query(default="main", min_length=1, max_length=200),
    path: str | None = Query(default=None, max_length=1000),
    limit: int = Query(default=30, ge=1, le=100),
):
    def op():
        history = GitHubClient().commits(ref, path, limit)
        data = [
            {
                "sha": item.get("sha"),
                "message": item.get("commit", {})
                .get("message", "")
                .splitlines()[0],
                "author": item.get("commit", {})
                .get("author", {})
                .get("name"),
                "authored_at": item.get("commit", {})
                .get("author", {})
                .get("date"),
                "html_url": item.get("html_url"),
            }
            for item in history
        ]
        return GitHubOperationResult(
            success=True,
            message="Commit history retrieved.",
            data=data,
        )

    return run(op)


@router.post("/branches", response_model=GitHubOperationResult)
def create_branch(payload: BranchCreateRequest):
    return run(
        lambda: GitHubOperationResult(
            success=True,
            message=f"Created {payload.branch_name}.",
            data=GitHubClient().create_branch(
                payload.branch_name,
                payload.base_branch,
            ),
        )
    )


@router.put("/files", response_model=GitHubOperationResult)
def write_file(payload: FileWriteRequest):
    return run(
        lambda: GitHubOperationResult(
            success=True,
            message=f"Committed {payload.path}.",
            data=GitHubClient().write_file(
                payload.path,
                payload.content,
                payload.branch,
                payload.commit_message,
                payload.existing_sha,
            ),
        )
    )


@router.post("/pull-requests", response_model=GitHubOperationResult)
def create_pr(payload: PullRequestCreateRequest):
    return run(
        lambda: GitHubOperationResult(
            success=True,
            message="Draft pull request created.",
            data=GitHubClient().create_pull_request(
                payload.title,
                payload.body,
                payload.head_branch,
                payload.base_branch,
                payload.draft,
            ),
        )
    )
