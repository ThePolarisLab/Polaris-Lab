from fastapi import APIRouter, HTTPException, Query

from app.code_understanding.analyzer import CodeAnalysisError, PythonCodeAnalyzer
from app.github_engine.client import GitHubClient, GitHubEngineError
from app.github_engine.schemas import GitHubOperationResult


router = APIRouter(
    prefix="/api/v1/code-understanding",
    tags=["Polaris Code Understanding Engine"],
)


def _read_python(path: str, ref: str) -> str:
    if not path.lower().endswith(".py"):
        raise CodeAnalysisError("PGE-003 v1 currently supports Python files only.")
    return GitHubClient().read_file(path, ref)["content"]


def _run(operation):
    try:
        return operation()
    except (GitHubEngineError, CodeAnalysisError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/analyze", response_model=GitHubOperationResult)
def analyze_file(
    path: str = Query(min_length=1, max_length=1000),
    ref: str = Query(default="main", min_length=1, max_length=200),
):
    def operation():
        source = _read_python(path, ref)
        analysis = PythonCodeAnalyzer().analyze(source, path)
        analysis["ref"] = ref
        return GitHubOperationResult(
            success=True,
            message=f"Analyzed {path}.",
            data=analysis,
        )

    return _run(operation)


@router.get("/explain", response_model=GitHubOperationResult)
def explain_file(
    path: str = Query(min_length=1, max_length=1000),
    ref: str = Query(default="main", min_length=1, max_length=200),
):
    def operation():
        source = _read_python(path, ref)
        analyzer = PythonCodeAnalyzer()
        return GitHubOperationResult(
            success=True,
            message=f"Explained {path}.",
            data={
                "path": path,
                "ref": ref,
                "explanation": analyzer.explain(source, path),
            },
        )

    return _run(operation)
