"""Assignment-local workspace discovery and boundary enforcement."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class WorkspaceError(RuntimeError):
    """Raised when an assignment workspace is invalid or out of bounds."""


@dataclass(frozen=True)
class Workspace:
    root: Path
    loop_dir: Path
    output_dir: Path

    @classmethod
    def discover(cls, path: str | Path = ".") -> "Workspace":
        candidate = Path(path).expanduser().resolve()
        if not candidate.exists():
            raise WorkspaceError(f"assignment directory does not exist: {candidate}")
        if not candidate.is_dir():
            raise WorkspaceError(f"assignment path is not a directory: {candidate}")
        return cls(candidate, candidate / ".loop", candidate / "output")

    def inside(self, path: str | Path) -> Path:
        """Resolve a path and prove it stays below the assignment root."""

        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        candidate = candidate.resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceError(f"path is outside assignment workspace: {candidate}") from exc
        return candidate

    def ensure_runtime_dirs(self) -> None:
        for relative in (
            ".loop",
            ".loop/sections",
            ".loop/reviews",
            ".loop/logs",
            ".loop/tasks",
            ".loop/agent-results",
            "output",
        ):
            self.inside(relative).mkdir(parents=True, exist_ok=True)

    def relative(self, path: str | Path) -> str:
        return self.inside(path).relative_to(self.root).as_posix()

    def find_input(self, name: str) -> Path | None:
        candidate = self.inside(name)
        return candidate if candidate.is_file() else None

    def input_manifest(self) -> dict[str, Any]:
        """Return references only; content remains in the source workspace."""

        assignment = self.find_input("assignment.md")
        if assignment is None:
            raise WorkspaceError(
                "assignment.md is required in the active assignment directory"
            )
        outline = self.find_input("outline.md")
        rubric = self.find_input("rubric.md")
        if rubric is None:
            rubric_pdf = self.find_input("rubric.pdf")
            rubric = rubric_pdf

        source_root = self.inside("sources")
        source_files: list[str] = []
        if source_root.is_dir():
            for file_path in sorted(path for path in source_root.rglob("*") if path.is_file()):
                source_files.append(self.relative(file_path))

        return {
            "workspace_root": str(self.root),
            "assignment_file": self.relative(assignment),
            "outline_file": self.relative(outline) if outline else None,
            "rubric_file": self.relative(rubric) if rubric else None,
            "source_files": source_files,
        }

    def source_index(self) -> list[dict[str, Any]]:
        manifest = self.input_manifest()
        result: list[dict[str, Any]] = []
        for index, relative in enumerate(manifest["source_files"], start=1):
            path = self.inside(relative)
            title = re.sub(r"[-_]+", " ", path.stem).strip().title()
            result.append(
                {
                    "id": f"S{index:02d}",
                    "title": title or path.name,
                    "authors": [],
                    "year": None,
                    "type": path.suffix.lower().lstrip(".") or "file",
                    "path": relative,
                    "url": None,
                    "verified": True,
                }
            )
        return result

    def read_input(self, relative: str | Path) -> str:
        path = self.inside(relative)
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ""
