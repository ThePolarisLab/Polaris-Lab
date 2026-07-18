from fastapi import APIRouter, HTTPException, Query

from app.code_understanding.analyzer import CodeAnalysisError, PythonCodeAnalyzer
from app.code_understanding.project import PythonProjectAnalyzer
from app.github_engine.client import GitHubClient, GitHubEngineError
from app.github_engine.schemas import GitHubOperationResult


router = APIRouter(
    prefix="/api/v1/code-understanding",
    tags=["Polaris Code Understanding Engine"],
)


def _read_python(path: str, ref: str) -> str:
    if not path.lower().endswith(".py"):
        raise CodeAnalysisError("PGE-003 currently supports Python files only.")
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
    chunked: bool = Query(default=False),
):
    def operation():
        source = _read_python(path, ref)
        analyzer = PythonCodeAnalyzer()
        analysis = (
            analyzer.analyze_chunked(source, path)
            if chunked
            else analyzer.analyze(source, path)
        )
        analysis["ref"] = ref
        return GitHubOperationResult(
            success=True,
            message=f"Analyzed {path} in {analysis['analysis_mode']} mode.",
            data=analysis,
        )

    return _run(operation)


@router.get("/explain", response_model=GitHubOperationResult)
def explain_file(
    path: str = Query(min_length=1, max_length=1000),
    ref: str = Query(default="main", min_length=1, max_length=200),
    chunked: bool = Query(default=False),
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
                "analysis_mode": "chunked" if chunked else "single",
                "explanation": analyzer.explain(source, path, chunked=chunked),
            },
        )

    return _run(operation)


@router.get("/project", response_model=GitHubOperationResult)
def analyze_project(
    root: str = Query(default="", max_length=1000),
    ref: str = Query(default="main", min_length=1, max_length=200),
    max_files: int = Query(default=200, ge=1, le=500),
):
    """Analyze Python dependencies across a repository subtree without executing code."""

    def operation():
        client = GitHubClient()
        clean_root = client.normalize_path(root)
        tree = client.repository_tree(ref=ref, recursive=True)
        if tree.get("truncated"):
            raise CodeAnalysisError(
                "GitHub returned a truncated repository tree; narrow the project root."
            )

        prefix = f"{clean_root}/" if clean_root else ""
        paths = sorted(
            item["path"]
            for item in tree.get("tree", [])
            if item.get("type") == "blob"
            and item.get("path", "").endswith(".py")
            and (not prefix or item.get("path", "").startswith(prefix))
            and "__pycache__" not in item.get("path", "").split("/")
        )
        if not paths:
            raise CodeAnalysisError("No Python files were found under the requested project root.")
        if len(paths) > max_files:
            raise CodeAnalysisError(
                f"Project contains {len(paths)} Python files; narrow the root or raise max_files."
            )

        files = {path: client.read_file(path, ref)["content"] for path in paths}
        analysis = PythonProjectAnalyzer(max_files=max_files).analyze(files, root=clean_root)
        analysis["ref"] = ref
        analysis["repository"] = client.repository
        return GitHubOperationResult(
            success=True,
            message=(
                f"Analyzed {analysis['metrics']['files']} Python files and "
                f"{analysis['metrics']['internal_dependencies']} internal dependencies."
            ),
            data=analysis,
        )

    return _run(operation)
