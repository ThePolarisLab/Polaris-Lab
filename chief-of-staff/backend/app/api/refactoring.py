"""HTTP API for deterministic refactoring analysis."""

from fastapi import APIRouter, HTTPException, Query

from app.github_engine.client import GitHubClient, GitHubEngineError
from app.github_engine.schemas import GitHubOperationResult
from app.refactoring.advisor import PythonRefactoringAdvisor
from app.refactoring.complexity import ComplexityAnalysisError, PythonComplexityAnalyzer
from app.refactoring.smells import PythonCodeSmellDetector


router = APIRouter(
    prefix="/api/v1/refactoring",
    tags=["Polaris Refactoring Advisor"],
)


def _run(operation):
    try:
        return operation()
    except (GitHubEngineError, ComplexityAnalysisError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _read_python_file(path: str, ref: str) -> tuple[GitHubClient, str]:
    if not path.lower().endswith(".py"):
        raise ComplexityAnalysisError("Polaris refactoring analysis currently supports Python files only.")
    client = GitHubClient()
    return client, client.read_file(path, ref)["content"]


@router.get("/complexity", response_model=GitHubOperationResult)
def analyze_complexity(
    path: str = Query(min_length=1, max_length=1000),
    ref: str = Query(default="main", min_length=1, max_length=200),
):
    """Analyze Python callable complexity in one repository file."""

    def operation():
        client, source = _read_python_file(path, ref)
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


@router.get("/smells", response_model=GitHubOperationResult)
def analyze_code_smells(
    path: str = Query(min_length=1, max_length=1000),
    ref: str = Query(default="main", min_length=1, max_length=200),
):
    """Detect deterministic Python code smells in one repository file."""

    def operation():
        client, source = _read_python_file(path, ref)
        analysis = PythonCodeSmellDetector().analyze(source, path)
        analysis["ref"] = ref
        analysis["repository"] = client.repository
        return GitHubOperationResult(
            success=True,
            message=(
                f"Detected {analysis['metrics']['total_findings']} code-smell findings "
                f"in {path}."
            ),
            data=analysis,
        )

    return _run(operation)


@router.get("/recommendations", response_model=GitHubOperationResult)
def analyze_refactoring_recommendations(
    path: str = Query(min_length=1, max_length=1000),
    ref: str = Query(default="main", min_length=1, max_length=200),
):
    """Generate a prioritized deterministic refactoring action plan."""

    def operation():
        client, source = _read_python_file(path, ref)
        analysis = PythonRefactoringAdvisor().analyze(source, path)
        analysis["ref"] = ref
        analysis["repository"] = client.repository
        return GitHubOperationResult(
            success=True,
            message=(
                f"Generated {analysis['metrics']['total_recommendations']} refactoring "
                f"recommendations for {path}."
            ),
            data=analysis,
        )

    return _run(operation)
