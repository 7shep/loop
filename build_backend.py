"""Minimal dependency-free PEP 517 backend for Loop.

Loop deliberately has no runtime dependencies. Keeping this backend local also
means a first install does not need setuptools in an isolated build environment.
"""

from __future__ import annotations

import base64
import hashlib
import os
import zipfile
from pathlib import Path


NAME = "loop-assignment-orchestrator"
NORMALIZED_NAME = NAME.replace("-", "_")
VERSION = "0.1.0"
DIST_INFO = f"{NORMALIZED_NAME}-{VERSION}.dist-info"
ROOT = Path(__file__).resolve().parent


def get_requires_for_build_wheel(config_settings=None):
    return []


def get_requires_for_build_editable(config_settings=None):
    return []


def _metadata() -> str:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    return (
        "Metadata-Version: 2.1\n"
        f"Name: {NAME}\n"
        f"Version: {VERSION}\n"
        "Summary: A review-gated, evidence-backed assignment workflow for Codex conversations.\n"
        "Author: Alex\n"
        "Requires-Python: >=3.11\n"
        "License: MIT\n"
        "Description-Content-Type: text/markdown\n\n"
        f"{readme}"
    )


def _wheel_metadata() -> str:
    return "Wheel-Version: 1.0\nGenerator: loop-build-backend\nRoot-Is-Purelib: true\nTag: py3-none-any\n"


def _entry_points() -> str:
    return "[console_scripts]\nloop = loop.cli:main\n"


def _package_files() -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    for path in sorted((ROOT / "src" / "loop").rglob("*.py")):
        files.append((path, path.relative_to(ROOT / "src").as_posix()))
    return files


def _write_wheel(destination: Path, editable: bool = False) -> str:
    records: list[tuple[str, str, str]] = []
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as wheel:
        if editable:
            files = [("loop-assignment-orchestrator.pth", str((ROOT / "src").resolve()))]
            for archive_name, content in files:
                data = content.encode("utf-8")
                wheel.writestr(archive_name, data)
                records.append((archive_name, _hash(data), str(len(data))))
        else:
            for path, archive_name in _package_files():
                data = path.read_bytes()
                wheel.writestr(archive_name, data)
                records.append((archive_name, _hash(data), str(len(data))))
        metadata_files = {
            f"{DIST_INFO}/METADATA": _metadata().encode("utf-8"),
            f"{DIST_INFO}/WHEEL": _wheel_metadata().encode("utf-8"),
            f"{DIST_INFO}/entry_points.txt": _entry_points().encode("utf-8"),
        }
        for archive_name, data in metadata_files.items():
            wheel.writestr(archive_name, data)
            records.append((archive_name, _hash(data), str(len(data))))
        record_name = f"{DIST_INFO}/RECORD"
        record = "\n".join(f"{name},{digest},{size}" for name, digest, size in records)
        record += f"\n{record_name},,\n"
        wheel.writestr(record_name, record.encode("utf-8"))
    return destination.name


def _hash(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return "sha256=" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    destination = Path(wheel_directory) / f"{NORMALIZED_NAME}-{VERSION}-py3-none-any.whl"
    return _write_wheel(destination)


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    destination = Path(wheel_directory) / f"{NORMALIZED_NAME}-{VERSION}-py3-none-any.whl"
    return _write_wheel(destination, editable=True)


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    target = Path(metadata_directory) / DIST_INFO
    target.mkdir(parents=True, exist_ok=True)
    (target / "METADATA").write_text(_metadata(), encoding="utf-8")
    (target / "WHEEL").write_text(_wheel_metadata(), encoding="utf-8")
    return DIST_INFO


def prepare_metadata_for_build_editable(metadata_directory, config_settings=None):
    return prepare_metadata_for_build_wheel(metadata_directory, config_settings)
