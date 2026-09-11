"""Persistent run-state helpers and controlled state transitions."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from .artifacts.store import ArtifactStore
from .models import RunPhase, RunState, RunStatus, SectionState, SectionStatus, utc_now


class StateError(RuntimeError):
    pass


STATE_PATH = ".loop/state.json"


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"run_{stamp}_{secrets.token_hex(3)}"


def create_state(
    workspace_root: str,
    loop_dir: str,
    output_dir: str,
    config: dict[str, Any],
    run_id: str | None = None,
) -> RunState:
    now = utc_now()
    return RunState(
        schema_version=1,
        run_id=run_id or new_run_id(),
        status=RunStatus.RUNNING.value,
        current_phase=RunPhase.INITIALIZING.value,
        workspace_root=workspace_root,
        loop_dir=loop_dir,
        output_dir=output_dir,
        created_at=now,
        updated_at=now,
        config=config,
    )


def load_state(store: ArtifactStore) -> RunState:
    if not store.exists(STATE_PATH):
        raise StateError("no Loop run exists in this assignment directory")
    try:
        state = RunState.from_dict(store.read_json(STATE_PATH))
    except (KeyError, TypeError, ValueError) as exc:
        raise StateError(f"invalid Loop state: {exc}") from exc
    if state.workspace_root != str(store.workspace.root):
        raise StateError("state workspace_root does not match the active assignment directory")
    return state


def save_state(store: ArtifactStore, state: RunState) -> None:
    state.updated_at = utc_now()
    store.write_json(STATE_PATH, state.to_dict())


def set_run_phase(state: RunState, phase: RunPhase) -> None:
    state.current_phase = phase.value


def set_section_status(state: RunState, section_id: str, status: SectionStatus) -> None:
    if section_id not in state.sections:
        raise StateError(f"unknown section: {section_id}")
    state.sections[section_id].status = status.value


def section_counts(state: RunState) -> dict[str, int]:
    counts: dict[str, int] = {}
    for section in state.sections.values():
        counts[section.status] = counts.get(section.status, 0) + 1
    return counts
