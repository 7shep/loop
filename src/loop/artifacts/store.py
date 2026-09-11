"""Atomic JSON/text artifact persistence under one workspace boundary."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from ..workspace import Workspace, WorkspaceError


class ArtifactError(RuntimeError):
    """Raised for missing or malformed Loop artifacts."""


class ArtifactStore:
    def __init__(self, workspace: Workspace):
        self.workspace = workspace
        workspace.ensure_runtime_dirs()

    def path(self, relative: str | Path) -> Path:
        return self.workspace.inside(relative)

    def exists(self, relative: str | Path) -> bool:
        return self.path(relative).exists()

    def write_text(self, relative: str | Path, value: str) -> Path:
        destination = self.path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(destination, value.encode("utf-8"))
        return destination

    def read_text(self, relative: str | Path) -> str:
        path = self.path(relative)
        if not path.is_file():
            raise ArtifactError(f"artifact does not exist: {self.workspace.relative(path)}")
        return path.read_text(encoding="utf-8")

    def write_json(self, relative: str | Path, value: Any) -> Path:
        try:
            content = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        except (TypeError, ValueError) as exc:
            raise ArtifactError(f"artifact is not JSON serialisable: {relative}") from exc
        return self.write_text(relative, content)

    def read_json(self, relative: str | Path) -> Any:
        try:
            return json.loads(self.read_text(relative))
        except json.JSONDecodeError as exc:
            raise ArtifactError(f"invalid JSON artifact: {relative}: {exc}") from exc

    def _atomic_write(self, destination: Path, content: bytes) -> None:
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=destination.parent, prefix=f".{destination.name}.", delete=False
            ) as handle:
                temporary = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        except OSError as exc:
            raise ArtifactError(f"could not write artifact: {destination}") from exc
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink(missing_ok=True)
