"""Structured event logging for CLI, future UI surfaces, and recovery diagnostics."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from .artifacts.store import ArtifactStore
from .models import utc_now


class EventLog:
    def __init__(self, store: ArtifactStore, run_id: str, reporter: Callable[[str], None] | None = None):
        self.store = store
        self.run_id = run_id
        self.reporter = reporter
        self.relative_path = ".loop/logs/events.jsonl"

    def emit(self, event_type: str, **data: Any) -> dict[str, Any]:
        event = {
            "event_id": uuid.uuid4().hex,
            "timestamp": utc_now(),
            "run_id": self.run_id,
            "type": event_type,
            "data": data,
        }
        path = self.store.path(self.relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        if self.reporter:
            self.reporter(self.message(event_type, data))
        return event

    @staticmethod
    def message(event_type: str, data: dict[str, Any]) -> str:
        section = data.get("section_id")
        suffix = f" [{section}]" if section else ""
        return f"[Loop] {event_type.lower().replace('_', ' ')}{suffix}"

    def tail(self, count: int = 20) -> list[dict[str, Any]]:
        path = self.store.path(self.relative_path)
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()[-count:]
        return [json.loads(line) for line in lines if line.strip()]
