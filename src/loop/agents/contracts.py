"""Provider-neutral contracts for isolated reasoning roles."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class AgentRole:
    name: str
    purpose: str
    input_schema: str
    output_schema: str
    allowed_reads: tuple[str, ...]
    allowed_writes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentTask:
    task_id: str
    run_id: str
    role: str
    mode: str
    input_refs: list[str]
    output_ref: str
    output_kind: str
    model: str
    effort: str
    timeout_seconds: int
    instructions: str
    metadata: dict[str, Any] = field(default_factory=dict)
    thread_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = "pending"
        return value


@dataclass
class AgentResult:
    status: str
    output: Any = None
    error: str | None = None


class AgentRuntime(Protocol):
    name: str

    def run(self, task: AgentTask, store: Any) -> AgentResult:
        """Run or queue one role task using artifact references, not transcripts."""


_ROLE_DEFINITIONS: dict[str, AgentRole] = {
    "orchestrator": AgentRole(
        "orchestrator",
        "Interpret assignment requirements and create the global section/dependency plan.",
        "assignment-manifest + assignment files",
        "global-plan",
        ("assignment.md", "outline.md", "rubric.md", "source-index.json"),
        ("global-plan.json", "task-graph.json", "state.json"),
    ),
    "planner": AgentRole(
        "planner",
        "Create one section's objective, claims, evidence requirements, structure, and word target.",
        "assignment + global plan + section context",
        "section-plan",
        ("assignment.md", "outline.md", "rubric.md", "global-plan.json", "section artifacts"),
        ("section plan.json",),
    ),
    "researcher": AgentRole(
        "researcher",
        "Gather traceable evidence for approved claims from permitted sources.",
        "approved section plan + source registry",
        "research + evidence records",
        ("sources/**", "source-index.json", "section plan.json"),
        ("research.json", "evidence.json"),
    ),
    "writer": AgentRole(
        "writer",
        "Draft a section using only its approved plan and registered evidence.",
        "approved plan + relevant evidence + style rules",
        "section draft",
        ("assignment.md", "section plan.json", "research.json", "evidence.json"),
        ("section draft.md",),
    ),
    "reviewer": AgentRole(
        "reviewer",
        "Critique a section plan or draft and return structured feedback without mutating accepted output.",
        "review target + requirements + evidence",
        "plan-review or writing-review",
        ("assignment.md", "global-plan.json", "section artifacts", "evidence.json"),
        ("plan-review.json", "writing-review.json"),
    ),
    "global_reviewer": AgentRole(
        "global_reviewer",
        "Audit the assembled document for assignment-wide quality and route affected sections.",
        "assembled draft + requirements + source registry",
        "global-review",
        ("output/final-draft.*", "assignment.md", "global-plan.json", "source-index.json"),
        ("reviews/global-review.json",),
    ),
}


def role_definitions() -> dict[str, AgentRole]:
    return dict(_ROLE_DEFINITIONS)
