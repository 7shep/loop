"""Small, serialisable domain models shared by the runtime and orchestrator."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RunStatus(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class RunPhase(str, Enum):
    INITIALIZING = "initializing"
    GLOBAL_PLANNING = "global_planning"
    SECTION_EXECUTION = "section_execution"
    ASSEMBLY = "assembly"
    GLOBAL_REVIEW = "global_review"
    COMPLETE = "complete"


class SectionStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    PLAN_REVIEW = "plan_review"
    RESEARCHING = "researching"
    WRITING = "writing"
    WRITING_REVIEW = "writing_review"
    APPROVED = "approved"
    COMMITTED = "committed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class Decision(str, Enum):
    APPROVE = "APPROVE"
    REVISE = "REVISE"
    PASS = "PASS"


@dataclass
class SectionState:
    id: str
    title: str
    order: int
    depends_on: list[str] = field(default_factory=list)
    status: str = SectionStatus.PENDING.value
    plan_revision: int = 0
    plan_review_attempts: int = 0
    writing_revision: int = 0
    writing_review_attempts: int = 0
    agent_failures: int = 0
    global_revision_count: int = 0
    last_error: str | None = None
    last_feedback: list[dict[str, Any]] = field(default_factory=list)
    affected_by_global_review: bool = False
    current_task_id: str | None = None
    paused_from: str | None = None
    committed_artifact: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SectionState":
        return cls(
            id=str(value["id"]),
            title=str(value["title"]),
            order=int(value.get("order", 0)),
            depends_on=[str(item) for item in value.get("depends_on", [])],
            status=str(value.get("status", SectionStatus.PENDING.value)),
            plan_revision=int(value.get("plan_revision", 0)),
            plan_review_attempts=int(value.get("plan_review_attempts", 0)),
            writing_revision=int(value.get("writing_revision", 0)),
            writing_review_attempts=int(value.get("writing_review_attempts", 0)),
            agent_failures=int(value.get("agent_failures", 0)),
            global_revision_count=int(value.get("global_revision_count", 0)),
            last_error=value.get("last_error"),
            last_feedback=list(value.get("last_feedback", [])),
            affected_by_global_review=bool(value.get("affected_by_global_review", False)),
            current_task_id=value.get("current_task_id"),
            paused_from=value.get("paused_from"),
            committed_artifact=value.get("committed_artifact"),
        )


@dataclass
class RunState:
    schema_version: int
    run_id: str
    status: str
    current_phase: str
    workspace_root: str
    loop_dir: str
    output_dir: str
    created_at: str
    updated_at: str
    sections: dict[str, SectionState] = field(default_factory=dict)
    graph: dict[str, Any] = field(default_factory=dict)
    global_review_cycle: int = 0
    agent_failures: int = 0
    agent_threads: dict[str, dict[str, Any]] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    last_error: str | None = None
    waiting_for_task: str | None = None
    # A parallel section batch can queue more than one conversation task
    # before the run pauses. Keep the original field as a compatibility alias
    # for callers that only understand one waiting task.
    waiting_for_tasks: list[str] = field(default_factory=list)
    termination_reason: str | None = None
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["sections"] = {key: section.to_dict() for key, section in self.sections.items()}
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RunState":
        return cls(
            schema_version=int(value.get("schema_version", 1)),
            run_id=str(value["run_id"]),
            status=str(value["status"]),
            current_phase=str(value.get("current_phase", RunPhase.INITIALIZING.value)),
            workspace_root=str(value["workspace_root"]),
            loop_dir=str(value["loop_dir"]),
            output_dir=str(value["output_dir"]),
            created_at=str(value.get("created_at", utc_now())),
            updated_at=str(value.get("updated_at", utc_now())),
            sections={
                key: SectionState.from_dict(section)
                for key, section in value.get("sections", {}).items()
            },
            graph=dict(value.get("graph", {})),
            global_review_cycle=int(value.get("global_review_cycle", 0)),
            agent_failures=int(value.get("agent_failures", 0)),
            agent_threads=dict(value.get("agent_threads", {})),
            config=dict(value.get("config", {})),
            last_error=value.get("last_error"),
            waiting_for_task=value.get("waiting_for_task"),
            waiting_for_tasks=[
                str(item)
                for item in value.get(
                    "waiting_for_tasks",
                    [value["waiting_for_task"]] if value.get("waiting_for_task") else [],
                )
            ],
            termination_reason=value.get("termination_reason"),
            completed_at=value.get("completed_at"),
        )
