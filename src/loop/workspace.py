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

    def outline_index(self) -> dict[str, Any]:
        """Return references for assignment guidance stored under ``outline/``.

        Outline materials are intentionally reference-only. This lets native
        Codex/Work agents inspect Markdown, text, PDF, or other permitted files
        with the tools available in their host environment without making the
        local orchestrator depend on a particular document parser.
        """

        outline_root = self.inside("outline")
        paths: list[Path] = []
        if outline_root.is_dir():
            paths.extend(path for path in outline_root.rglob("*") if path.is_file())

        # Keep existing assignment folders usable while the outline/ folder is
        # adopted. These are compatibility inputs, not the canonical layout.
        for name in ("outline.md", "outline.pdf", "outline.txt", "rubric.md", "rubric.pdf", "rubric.txt"):
            candidate = self.find_input(name)
            if candidate is not None:
                paths.append(candidate)

        unique_paths: list[Path] = []
        seen: set[Path] = set()
        for path in sorted(paths, key=lambda item: self.relative(item)):
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                unique_paths.append(resolved)

        groups: dict[str, Any] = {
            "outline_files": [],
            "assignment_outline_files": [],
            "rubric_files": [],
            "past_marks_files": [],
            "other_guidance_files": [],
            "legacy_files": [],
        }
        for path in unique_paths:
            relative = self.relative(path)
            groups["outline_files"].append(relative)
            if path.parent == self.root:
                groups["legacy_files"].append(relative)
            for category in self._outline_categories(path.stem):
                groups[category].append(relative)

        groups["outline_dir"] = "outline" if outline_root.is_dir() else None
        groups["past_mark_guidance"] = {
            "purpose": "Use prior professor feedback and lost-mark records as preventive guidance.",
            "must_do": [
                "Read every listed past-mark or feedback artifact before planning or drafting.",
                "Extract recurring, concrete reasons marks were lost and turn them into do/not-do checks.",
                "Apply those checks in section plans, writing, and review decisions when they do not conflict with the current assignment.",
            ],
            "must_not_do": [
                "Do not treat historical feedback as a replacement for the current assignment outline or rubric.",
                "Do not invent past mistakes or assume an issue applies when the records do not support it.",
                "Do not copy prior assignment content; use the records only to improve compliance and quality.",
            ],
        }
        return groups

    def _outline_categories(self, stem: str) -> list[str]:
        normalized = re.sub(r"[^a-z0-9]+", "-", stem.lower())
        categories: list[str] = []
        if any(
            token in normalized
            for token in ("past", "previous", "feedback", "deduction", "lost", "comment", "professor")
        ):
            categories.append("past_marks_files")
        if any(token in normalized for token in ("rubric", "grading", "marking", "criteria")):
            categories.append("rubric_files")
        if any(token in normalized for token in ("outline", "brief", "requirement", "instruction", "prompt", "assignment")):
            categories.append("assignment_outline_files")
        return categories or ["other_guidance_files"]

    def input_manifest(self) -> dict[str, Any]:
        """Return references only; content remains in the source workspace."""

        assignment = self.find_input("assignment.md")
        if assignment is None:
            raise WorkspaceError(
                "assignment.md is required in the active assignment directory"
            )
        outline_index = self.outline_index()
        assignment_outline_files = outline_index["assignment_outline_files"]
        rubric_files = outline_index["rubric_files"]

        source_root = self.inside("sources")
        source_files: list[str] = []
        if source_root.is_dir():
            for file_path in sorted(path for path in source_root.rglob("*") if path.is_file()):
                source_files.append(self.relative(file_path))

        return {
            "workspace_root": str(self.root),
            "assignment_file": self.relative(assignment),
            # Singular fields remain as a compatibility convenience for older
            # consumers; the collection fields are authoritative.
            "outline_file": assignment_outline_files[0] if assignment_outline_files else None,
            "rubric_file": rubric_files[0] if rubric_files else None,
            "outline_dir": outline_index["outline_dir"],
            "outline_files": outline_index["outline_files"],
            "assignment_outline_files": assignment_outline_files,
            "rubric_files": rubric_files,
            "past_marks_files": outline_index["past_marks_files"],
            "other_guidance_files": outline_index["other_guidance_files"],
            "legacy_outline_files": outline_index["legacy_files"],
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
