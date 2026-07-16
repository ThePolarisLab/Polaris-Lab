from fastapi import APIRouter, HTTPException
from app.github_engine.client import GitHubClient, GitHubEngineError
from app.github_engine.schemas import BranchCreateRequest, FileWriteRequest, PullRequestCreateRequest, GitHubOperationResult

router = APIRouter(prefix="/api/v1/github", tags=["Polaris GitHub Engine"])

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
        return GitHubOperationResult(success=True, message="GitHub Engine connected.", data={
            "repository": repo["full_name"],
            "default_branch": repo["default_branch"],
            "private": repo["private"],
            "write_enabled": client.write_enabled,
            "permissions": repo.get("permissions"),
        })
    return run(op)

@router.get("/branches", response_model=GitHubOperationResult)
def branches():
    return run(lambda: GitHubOperationResult(
        success=True,
        message="Branches retrieved.",
        data=[{"name": b["name"], "sha": b["commit"]["sha"], "protected": b.get("protected", False)}
              for b in GitHubClient().branches()]
    ))

@router.post("/branches", response_model=GitHubOperationResult)
def create_branch(payload: BranchCreateRequest):
    return run(lambda: GitHubOperationResult(
        success=True,
        message=f"Created {payload.branch_name}.",
        data=GitHubClient().create_branch(payload.branch_name, payload.base_branch)
    ))

@router.put("/files", response_model=GitHubOperationResult)
def write_file(payload: FileWriteRequest):
    return run(lambda: GitHubOperationResult(
        success=True,
        message=f"Committed {payload.path}.",
        data=GitHubClient().write_file(payload.path, payload.content, payload.branch, payload.commit_message, payload.existing_sha)
    ))

@router.post("/pull-requests", response_model=GitHubOperationResult)
def create_pr(payload: PullRequestCreateRequest):
    return run(lambda: GitHubOperationResult(
        success=True,
        message="Draft pull request created.",
        data=GitHubClient().create_pull_request(payload.title, payload.body, payload.head_branch, payload.base_branch, payload.draft)
    ))
