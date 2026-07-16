from pydantic import BaseModel, Field

class BranchCreateRequest(BaseModel):
    branch_name: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._/-]+$")
    base_branch: str = "main"

class FileWriteRequest(BaseModel):
    path: str
    content: str
    branch: str
    commit_message: str
    existing_sha: str | None = None

class PullRequestCreateRequest(BaseModel):
    title: str
    body: str = ""
    head_branch: str
    base_branch: str = "main"
    draft: bool = True

class GitHubOperationResult(BaseModel):
    success: bool
    message: str
    data: dict | list | None = None
