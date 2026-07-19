"""HTTP API for deterministic refactoring analysis."""

from fastapi import APIRouter, HTTPException, Query

from app.github_engine.client import GitHubClient, GitHubEngineError
from app.github_engine.schemas import GitHubOperationResult
from app.refactoring.complexity import ComplexityAnalysisError, PythonComplexityAnalyzer


router = APIRouter(
    prefix="/api/v1/refactoring",
    tags=["Polaris Refactoring Advisor"],
)


def _run(operation):
    try:
        return operation()
    except (GitHubEngineError, ComplexityAnalysisError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/complexity", response_model=GitHubOperationResult)
def analyze_complexity(
    path: str = Query(min_length=1, max_length=1000),
    ref: str = Query(default="main", min_length=1, max_length=200),
):
    """Analyze Python callable complexity in one repository file."""

    def operation():
        if not path.lower().endswith(".py"):
            raise ComplexityAnalysisError("PGE-004.1 currently supports Python files only.")
        client = GitHubClient()
        source = client.read_file(path, ref)["content"]
        analysis = PythonComplexityAnalyzer().analyze(source, path)
        analysis["ref"] = ref
        analysis["repository"] = client.repository
        return GitHubOperationResult(
            success=True,
            message=(
                f"Analyzed {analysis['metrics']['total_callables']} callables in {path}; "
                f"maximum complexity is {analysis['metrics']['maximum_complexity']}."
            ),
            data=analysis,
        )

    return _run(operation)
