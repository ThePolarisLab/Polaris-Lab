from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath

from app.code_understanding.analyzer import CodeAnalysisError, PythonCodeAnalyzer


class PythonProjectAnalyzer:
    """Build a deterministic dependency model for a set of Python files.

    The analyzer parses source with :class:`PythonCodeAnalyzer`; it never imports
    or executes repository code.
    """

    DEFAULT_MAX_FILES = 500

    def __init__(
        self,
        *,
        file_analyzer: PythonCodeAnalyzer | None = None,
        max_files: int = DEFAULT_MAX_FILES,
    ) -> None:
        if isinstance(max_files, bool) or max_files <= 0:
            raise CodeAnalysisError("The project file limit must be a positive integer.")
        self.file_analyzer = file_analyzer or PythonCodeAnalyzer()
        self.max_files = max_files

    def analyze(self, files: dict[str, str], root: str = "") -> dict:
        normalized = self._normalize_files(files, root)
        if not normalized:
            raise CodeAnalysisError("No Python files were supplied for project analysis.")
        if len(normalized) > self.max_files:
            raise CodeAnalysisError(
                f"Project contains {len(normalized)} Python files; the configured limit is {self.max_files}."
            )

        path_to_module = {path: self._module_name(path) for path in normalized}
        module_to_path = {module: path for path, module in path_to_module.items()}
        analyses: dict[str, dict] = {}
        nodes: list[dict] = []

        for path, source in sorted(normalized.items()):
            analysis = self.file_analyzer.analyze(source, path)
            module = path_to_module[path]
            analyses[module] = analysis
            nodes.append(
                {
                    "module": module,
                    "path": path,
                    "package": self._package_name(module, path),
                    "metrics": analysis["metrics"],
                    "summary": analysis["summary"],
                }
            )

        edges: list[dict] = []
        external_dependencies: set[str] = set()
        unresolved_internal: list[dict] = []
        adjacency: dict[str, set[str]] = {module: set() for module in module_to_path}

        for source_module, analysis in sorted(analyses.items()):
            source_path = module_to_path[source_module]
            for item in analysis["imports"]:
                target = self._resolve_import(
                    source_module=source_module,
                    source_path=source_path,
                    imported_module=item["module"],
                    imported_name=item["name"],
                    known_modules=set(module_to_path),
                )
                edge = {
                    "source": source_module,
                    "target": target,
                    "import_module": item["module"],
                    "imported_name": item["name"],
                    "alias": item["alias"],
                    "line": item["line"],
                    "resolved": target is not None,
                    "kind": "internal" if target is not None else "external",
                }
                edges.append(edge)
                if target is not None:
                    adjacency[source_module].add(target)
                else:
                    top_level = item["module"].lstrip(".").split(".", 1)[0]
                    if top_level:
                        external_dependencies.add(top_level)
                    elif item["name"]:
                        unresolved_internal.append(
                            {
                                "source": source_module,
                                "module": item["module"],
                                "name": item["name"],
                                "line": item["line"],
                            }
                        )

        reverse = self._reverse_dependencies(adjacency)
        cycles = self._cycles(adjacency)
        packages = self._package_summaries(nodes, adjacency)
        entry_modules = sorted(module for module, inbound in reverse.items() if not inbound)
        leaf_modules = sorted(module for module, outbound in adjacency.items() if not outbound)

        return {
            "language": "python",
            "root": root.strip("/"),
            "analysis_mode": "project",
            "file_limit": self.max_files,
            "metrics": {
                "files": len(nodes),
                "modules": len(nodes),
                "packages": len(packages),
                "internal_dependencies": sum(len(targets) for targets in adjacency.values()),
                "external_dependencies": len(external_dependencies),
                "cycles": len(cycles),
            },
            "modules": nodes,
            "dependencies": sorted(
                edges,
                key=lambda item: (
                    item["source"],
                    item["target"] or "",
                    item["line"],
                    item["imported_name"] or "",
                ),
            ),
            "dependency_graph": {
                module: sorted(targets) for module, targets in sorted(adjacency.items())
            },
            "reverse_dependencies": {
                module: sorted(sources) for module, sources in sorted(reverse.items())
            },
            "cycles": cycles,
            "entry_modules": entry_modules,
            "leaf_modules": leaf_modules,
            "external_dependencies": sorted(external_dependencies),
            "unresolved_relative_imports": unresolved_internal,
            "packages": packages,
        }

    @staticmethod
    def _normalize_files(files: dict[str, str], root: str) -> dict[str, str]:
        clean_root = root.strip().strip("/")
        result: dict[str, str] = {}
        for raw_path, source in files.items():
            path = str(PurePosixPath(raw_path.strip().replace("\\", "/"))).lstrip("/")
            if clean_root:
                prefix = f"{clean_root}/"
                if not path.startswith(prefix):
                    continue
                path = path[len(prefix) :]
            if path.endswith(".py") and "__pycache__" not in PurePosixPath(path).parts:
                result[path] = source
        return result

    @staticmethod
    def _module_name(path: str) -> str:
        parts = list(PurePosixPath(path).parts)
        filename = parts.pop()
        stem = filename[:-3]
        if stem != "__init__":
            parts.append(stem)
        return ".".join(parts) or stem

    @staticmethod
    def _package_name(module: str, path: str) -> str:
        if path.endswith("/__init__.py") or path == "__init__.py":
            return module
        return module.rpartition(".")[0]

    def _resolve_import(
        self,
        *,
        source_module: str,
        source_path: str,
        imported_module: str,
        imported_name: str | None,
        known_modules: set[str],
    ) -> str | None:
        level = len(imported_module) - len(imported_module.lstrip("."))
        base = imported_module.lstrip(".")

        if level:
            package = self._package_name(source_module, source_path)
            package_parts = package.split(".") if package else []
            climb = level - 1
            if climb > len(package_parts):
                return None
            prefix_parts = package_parts[: len(package_parts) - climb]
            if base:
                prefix_parts.extend(base.split("."))
            base = ".".join(part for part in prefix_parts if part)

        candidates: list[str] = []
        if base:
            candidates.append(base)
            if imported_name and imported_name != "*":
                candidates.insert(0, f"{base}.{imported_name}")
        elif imported_name and imported_name != "*":
            candidates.append(imported_name)

        for candidate in candidates:
            if candidate in known_modules:
                return candidate

        # ``import package.module`` may refer to a known parent package only.
        parts = base.split(".") if base else []
        while len(parts) > 1:
            parts.pop()
            candidate = ".".join(parts)
            if candidate in known_modules:
                return candidate
        return None

    @staticmethod
    def _reverse_dependencies(adjacency: dict[str, set[str]]) -> dict[str, set[str]]:
        reverse = {module: set() for module in adjacency}
        for source, targets in adjacency.items():
            for target in targets:
                reverse[target].add(source)
        return reverse

    @staticmethod
    def _cycles(adjacency: dict[str, set[str]]) -> list[list[str]]:
        index = 0
        stack: list[str] = []
        on_stack: set[str] = set()
        indices: dict[str, int] = {}
        lowlinks: dict[str, int] = {}
        components: list[list[str]] = []

        def visit(module: str) -> None:
            nonlocal index
            indices[module] = index
            lowlinks[module] = index
            index += 1
            stack.append(module)
            on_stack.add(module)

            for target in sorted(adjacency[module]):
                if target not in indices:
                    visit(target)
                    lowlinks[module] = min(lowlinks[module], lowlinks[target])
                elif target in on_stack:
                    lowlinks[module] = min(lowlinks[module], indices[target])

            if lowlinks[module] == indices[module]:
                component: list[str] = []
                while True:
                    item = stack.pop()
                    on_stack.remove(item)
                    component.append(item)
                    if item == module:
                        break
                component.sort()
                if len(component) > 1 or module in adjacency[module]:
                    components.append(component)

        for module in sorted(adjacency):
            if module not in indices:
                visit(module)
        return sorted(components)

    @staticmethod
    def _package_summaries(nodes: list[dict], adjacency: dict[str, set[str]]) -> list[dict]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for node in nodes:
            grouped[node["package"]].append(node["module"])

        summaries: list[dict] = []
        for package, modules in sorted(grouped.items()):
            module_set = set(modules)
            internal_edges = sum(
                1
                for source in modules
                for target in adjacency[source]
                if target in module_set
            )
            outbound = sorted(
                {
                    target
                    for source in modules
                    for target in adjacency[source]
                    if target not in module_set
                }
            )
            summaries.append(
                {
                    "package": package,
                    "modules": sorted(modules),
                    "module_count": len(modules),
                    "internal_dependencies": internal_edges,
                    "outbound_dependencies": outbound,
                }
            )
        return summaries
