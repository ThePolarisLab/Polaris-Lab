import pytest

from app.code_understanding.analyzer import CodeAnalysisError
from app.code_understanding.project import PythonProjectAnalyzer


FILES = {
    "app/__init__.py": "",
    "app/main.py": "from .services import worker\nfrom app.models import User\nimport requests\n",
    "app/services/__init__.py": "",
    "app/services/worker.py": "from ..models import User\nfrom . import helpers\n",
    "app/services/helpers.py": "from app.models import User\n",
    "app/models.py": "class User:\n    pass\n",
}


def test_project_analyzer_builds_internal_dependency_graph():
    result = PythonProjectAnalyzer().analyze(FILES)

    assert result["analysis_mode"] == "project"
    assert result["metrics"]["files"] == 6
    assert result["dependency_graph"]["app.main"] == [
        "app.models",
        "app.services.worker",
    ]
    assert result["dependency_graph"]["app.services.worker"] == [
        "app.models",
        "app.services.helpers",
    ]
    assert result["reverse_dependencies"]["app.models"] == [
        "app.main",
        "app.services.helpers",
        "app.services.worker",
    ]


def test_project_analyzer_reports_external_dependencies():
    result = PythonProjectAnalyzer().analyze(FILES)

    assert result["external_dependencies"] == ["requests"]
    external = [edge for edge in result["dependencies"] if edge["kind"] == "external"]
    assert external[0]["source"] == "app.main"
    assert external[0]["import_module"] == "requests"


def test_project_analyzer_maps_packages_and_entry_modules():
    result = PythonProjectAnalyzer().analyze(FILES)

    packages = {item["package"]: item for item in result["packages"]}
    assert packages["app.services"]["module_count"] == 3
    assert "app.main" in result["entry_modules"]
    assert "app.models" in result["leaf_modules"]


def test_project_analyzer_detects_dependency_cycles():
    files = {
        "pkg/a.py": "from . import b\n",
        "pkg/b.py": "from . import c\n",
        "pkg/c.py": "from . import a\n",
    }
    result = PythonProjectAnalyzer().analyze(files)

    assert result["cycles"] == [["pkg.a", "pkg.b", "pkg.c"]]
    assert result["metrics"]["cycles"] == 1


def test_project_root_filters_and_relativizes_paths():
    files = {
        "backend/app/one.py": "from app import two\n",
        "backend/app/two.py": "",
        "frontend/tool.py": "",
    }
    result = PythonProjectAnalyzer().analyze(files, root="backend")

    assert [item["path"] for item in result["modules"]] == ["app/one.py", "app/two.py"]
    assert result["dependency_graph"]["app.one"] == ["app.two"]


def test_project_file_limit_is_enforced():
    with pytest.raises(CodeAnalysisError, match="configured limit"):
        PythonProjectAnalyzer(max_files=1).analyze({"a.py": "", "b.py": ""})


def test_project_requires_python_files():
    with pytest.raises(CodeAnalysisError, match="No Python files"):
        PythonProjectAnalyzer().analyze({"README.md": "text"})


def test_project_analysis_rejects_invalid_python():
    with pytest.raises(CodeAnalysisError, match="Invalid Python syntax"):
        PythonProjectAnalyzer().analyze({"broken.py": "def broken(:"})
