"""Deterministic Loop state machine around provider-neutral agent roles."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from .agents.contracts import AgentResult, AgentRuntime, AgentTask, role_definitions
from .agents.demo import DemoAgentRuntime
from .artifacts.store import ArtifactStore
from .config import LoopConfig, load_config
from .document import assemble_latex, assemble_markdown
from .events import EventLog
from .graph import TaskGraph
from .models import RunPhase, RunState, RunStatus, SectionState, SectionStatus, utc_now
from .schemas import (
    SchemaError,
    validate_global_plan,
    validate_global_review,
    validate_plan_review,
    validate_research,
    validate_section_plan,
    validate_writing_review,
)
from .state import create_state, load_state, save_state, section_counts, set_run_phase
from .runtime.codex_runtime import CodexConversationRuntime
from .workspace import Workspace


class OrchestrationError(RuntimeError):
    pass


class ConversationPaused(OrchestrationError):
    pass


class AgentExecutionError(OrchestrationError):
    pass


@dataclass
class RunResult:
    status: str
    run_id: str
    message: str


class LoopOrchestrator:
    """Own all state transitions and all writes to accepted section artifacts."""

    def __init__(
        self,
        workspace: Workspace,
        config: LoopConfig | None = None,
        runtime: AgentRuntime | None = None,
        reporter: Callable[[str], None] | None = None,
        request: str | None = None,
    ) -> None:
        self.workspace = workspace
        self.store = ArtifactStore(workspace)
        self.config = config or load_config(workspace.root)
        self.runtime = runtime or (
            DemoAgentRuntime() if self.config.runtime == "demo" else CodexConversationRuntime()
        )
        self.reporter = reporter
        self.request = request.strip() if request and request.strip() else None
        self.state: RunState | None = None
        self.events: EventLog | None = None

    def run(self, resume: bool = False) -> RunResult:
        self._load_or_initialize()
        assert self.state is not None
        if self.state.status in {
            RunStatus.COMPLETED.value,
            RunStatus.FAILED.value,
            RunStatus.CANCELLED.value,
        }:
            return RunResult(self.state.status, self.state.run_id, self._terminal_message())
        if self.state.status == RunStatus.PAUSED.value and not resume:
            return RunResult("paused", self.state.run_id, self._waiting_message())
        if resume:
            self._restore_paused_sections()
        self.state.status = RunStatus.RUNNING.value
        self.state.waiting_for_task = None
        save_state(self.store, self.state)
        if self.events:
            self.events.emit("RUN_RESUMED" if resume else "RUN_STARTED", phase=self.state.current_phase)

        try:
            while True:
                if self.state.status != RunStatus.RUNNING.value:
                    break
                if not self.state.sections:
                    self._create_global_plan()
                    if not self.state.sections:
                        continue
                unfinished = [
                    section for section in self.state.sections.values() if section.status != SectionStatus.COMMITTED.value
                ]
                if unfinished:
                    set_run_phase(self.state, RunPhase.SECTION_EXECUTION)
                    save_state(self.store, self.state)
                    runnable = self._runnable_sections()
                    if not runnable:
                        self._fail_run("dependency deadlock: no unfinished section is runnable")
                        break
                    # The batch boundary is explicit and bounded. The first runtime is
                    # serial for deterministic artifact updates; the graph and batch
                    # limit are ready for a concurrent provider implementation.
                    for section in runnable[: self.config.limits.max_parallel_sections]:
                        self._run_section(section)
                        if self.state.status != RunStatus.RUNNING.value:
                            break
                    continue
                if not self._assemble_and_review():
                    break
                if self.state.status == RunStatus.COMPLETED.value:
                    break
        except ConversationPaused:
            # The task manifest is the handoff point for the active Codex/Work session.
            pass
        except OrchestrationError as exc:
            self._fail_run(str(exc))
        except Exception as exc:  # ensure unexpected failures are resumable and visible
            self._fail_run(f"unexpected orchestration error: {exc}")

        assert self.state is not None
        return RunResult(self.state.status, self.state.run_id, self._status_message())

    def pause(self) -> RunResult:
        self._load_or_initialize(require_existing=True)
        assert self.state is not None
        if self.state.status == RunStatus.RUNNING.value:
            self.state.status = RunStatus.PAUSED.value
            self.state.waiting_for_task = None
            save_state(self.store, self.state)
            if self.events:
                self.events.emit("RUN_PAUSED", phase=self.state.current_phase)
        return RunResult(self.state.status, self.state.run_id, "run paused")

    def cancel(self) -> RunResult:
        self._load_or_initialize(require_existing=True)
        assert self.state is not None
        if self.state.status not in {RunStatus.COMPLETED.value, RunStatus.FAILED.value}:
            self.state.status = RunStatus.CANCELLED.value
            self.state.termination_reason = "cancelled by user"
            save_state(self.store, self.state)
            if self.events:
                self.events.emit("RUN_CANCELLED")
        return RunResult(self.state.status, self.state.run_id, "run cancelled")

    def status_snapshot(self) -> dict[str, Any]:
        self._load_or_initialize(require_existing=True)
        assert self.state is not None
        return {
            "run_id": self.state.run_id,
            "status": self.state.status,
            "phase": self.state.current_phase,
            "workspace_root": self.state.workspace_root,
            "output_dir": self.state.output_dir,
            "sections": section_counts(self.state),
            "global_review_cycle": self.state.global_review_cycle,
            "agent_failures": self.state.agent_failures,
            "agent_threads": self.state.agent_threads,
            "waiting_for_task": self.state.waiting_for_task,
            "last_error": self.state.last_error,
            "termination_reason": self.state.termination_reason,
        }

    def _load_or_initialize(self, require_existing: bool = False) -> None:
        if self.store.exists(".loop/state.json"):
            self.state = load_state(self.store)
            self.config = LoopConfig.from_dict(self.state.config)
            self.events = EventLog(self.store, self.state.run_id, self.reporter)
            return
        if require_existing:
            raise OrchestrationError("no Loop run exists in this assignment directory")
        manifest = self.workspace.input_manifest()
        self.state = create_state(
            workspace_root=str(self.workspace.root),
            loop_dir=str(self.workspace.loop_dir),
            output_dir=str(self.workspace.output_dir),
            config=self.config.to_dict(),
        )
        self.events = EventLog(self.store, self.state.run_id, self.reporter)
        if self.request:
            self.store.write_text(".loop/request.md", self.request + "\n")
            manifest["user_request_file"] = ".loop/request.md"
        self.store.write_json(".loop/assignment.json", manifest)
        self.store.write_json(".loop/source-index.json", {"sources": self.workspace.source_index()})
        self.store.write_json(".loop/evidence.json", {"evidence": []})
        save_state(self.store, self.state)
        self.events.emit("RUN_INITIALIZED", workspace_root=str(self.workspace.root))

    def _create_global_plan(self) -> None:
        assert self.state is not None and self.events is not None
        set_run_phase(self.state, RunPhase.GLOBAL_PLANNING)
        save_state(self.store, self.state)
        self.events.emit("GLOBAL_PLAN_STARTED")
        manifest = self.store.read_json(".loop/assignment.json")
        refs = [manifest["assignment_file"]]
        if manifest.get("user_request_file"):
            refs.append(manifest["user_request_file"])
        if manifest.get("outline_file"):
            refs.append(manifest["outline_file"])
        if manifest.get("rubric_file"):
            refs.append(manifest["rubric_file"])
        refs.append(".loop/source-index.json")
        task = self._task(
            role="orchestrator",
            mode="global_plan",
            input_refs=refs,
            output_ref=".loop/global-plan.json",
            output_kind="json",
            instructions="Create a validated global section/dependency plan from the assignment artifacts.",
        )
        try:
            value = self._invoke(task)
        except AgentExecutionError as exc:
            self.state.agent_failures += 1
            self.state.last_error = str(exc)
            if self.state.agent_failures > self.config.limits.max_agent_failures:
                self._fail_run("global planning agent failure limit reached")
            else:
                save_state(self.store, self.state)
                self.events.emit("AGENT_RETRY_SCHEDULED", role="orchestrator", attempt=self.state.agent_failures)
            return
        plan = validate_global_plan(value)
        self.store.write_json(".loop/global-plan.json", plan)
        graph = TaskGraph.from_global_plan(plan)
        self.state.graph = graph.to_dict()
        self.state.sections = {
            section["id"]: SectionState(
                id=section["id"],
                title=section["title"],
                order=section["order"],
                depends_on=list(section.get("depends_on", [])),
            )
            for section in plan["sections"]
        }
        self._persist_graph()
        save_state(self.store, self.state)
        self.events.emit("GLOBAL_PLAN_CREATED", section_count=len(self.state.sections))

    def _runnable_sections(self) -> list[SectionState]:
        assert self.state is not None
        committed = {
            section.id for section in self.state.sections.values() if section.status == SectionStatus.COMMITTED.value
        }
        return sorted(
            (
                section
                for section in self.state.sections.values()
                if section.status not in {
                    SectionStatus.COMMITTED.value,
                    SectionStatus.FAILED.value,
                    SectionStatus.CANCELLED.value,
                }
                and all(dependency in committed for dependency in section.depends_on)
            ),
            key=lambda item: item.order,
        )

    def _run_section(self, section: SectionState) -> None:
        assert self.state is not None and self.events is not None
        self.events.emit("SECTION_STARTED", section_id=section.id, status=section.status)
        try:
            while self.state.status == RunStatus.RUNNING.value:
                if section.status == SectionStatus.PENDING.value:
                    self._transition(section, SectionStatus.PLANNING)
                elif section.status == SectionStatus.PLANNING.value:
                    if not section.current_task_id:
                        section.plan_revision += 1
                    self._transition(section, SectionStatus.PLANNING)
                    value = self._invoke(
                        self._task(
                            role="planner",
                            mode="section_plan",
                            section=section,
                            input_refs=self._section_input_refs(),
                            output_ref=self._section_ref(section, "plan.json"),
                            output_kind="json",
                            instructions="Create the structured plan for this section; do not write final prose.",
                        ),
                        section=section,
                    )
                    self.store.write_json(self._section_ref(section, "plan.json"), validate_section_plan(value))
                    self._transition(section, SectionStatus.PLAN_REVIEW)
                elif section.status == SectionStatus.PLAN_REVIEW.value:
                    value = self._invoke(
                        self._task(
                            role="reviewer",
                            mode="plan_review",
                            section=section,
                            input_refs=[self._section_ref(section, "plan.json"), ".loop/global-plan.json", "assignment.md"],
                            output_ref=self._section_ref(section, "plan-review.json"),
                            output_kind="json",
                            instructions="Critique the section plan and return APPROVE or REVISE with structured issues.",
                        ),
                        section=section,
                    )
                    review = validate_plan_review(value)
                    self.store.write_json(self._section_ref(section, "plan-review.json"), review)
                    section.plan_review_attempts += 1
                    if review["decision"] == "APPROVE":
                        self._transition(section, SectionStatus.RESEARCHING)
                    elif section.plan_revision > self.config.limits.max_plan_revisions:
                        self._fail_section(section, "plan revision limit reached")
                        return
                    else:
                        section.last_feedback = review.get("issues", [])
                        self._reset_graph_from(section.id, "plan")
                        self._transition(section, SectionStatus.PLANNING)
                        self.events.emit("PLAN_REJECTED", section_id=section.id)
                elif section.status == SectionStatus.RESEARCHING.value:
                    value = self._invoke(
                        self._task(
                            role="researcher",
                            mode="research",
                            section=section,
                            input_refs=[self._section_ref(section, "plan.json"), ".loop/source-index.json"],
                            output_ref=self._section_ref(section, "research.json"),
                            output_kind="json",
                            instructions="Gather traceable evidence for the approved claims; do not write final prose.",
                        ),
                        section=section,
                    )
                    research = validate_research(value)
                    self.store.write_json(self._section_ref(section, "research.json"), research)
                    self._merge_evidence(research)
                    self._transition(section, SectionStatus.WRITING)
                elif section.status == SectionStatus.WRITING.value:
                    if not section.current_task_id:
                        section.writing_revision += 1
                    value = self._invoke(
                        self._task(
                            role="writer",
                            mode="section_draft",
                            section=section,
                            input_refs=[
                                self._section_ref(section, "plan.json"),
                                self._section_ref(section, "research.json"),
                                ".loop/evidence.json",
                            ],
                            output_ref=self._section_ref(section, "draft.md"),
                            output_kind="text",
                            instructions="Write only this section using registered evidence and internal citation markers.",
                        ),
                        section=section,
                    )
                    if not isinstance(value, str) or not value.strip():
                        raise SchemaError("writer output must be non-empty text")
                    self.store.write_text(self._section_ref(section, "draft.md"), value)
                    self._transition(section, SectionStatus.WRITING_REVIEW)
                elif section.status == SectionStatus.WRITING_REVIEW.value:
                    value = self._invoke(
                        self._task(
                            role="reviewer",
                            mode="writing_review",
                            section=section,
                            input_refs=[
                                self._section_ref(section, "draft.md"),
                                self._section_ref(section, "plan.json"),
                                self._section_ref(section, "research.json"),
                                ".loop/evidence.json",
                                "assignment.md",
                            ],
                            output_ref=self._section_ref(section, "writing-review.json"),
                            output_kind="json",
                            instructions="Evaluate the draft and return structured APPROVE or REVISE feedback.",
                        ),
                        section=section,
                    )
                    review = validate_writing_review(value)
                    self.store.write_json(self._section_ref(section, "writing-review.json"), review)
                    section.writing_review_attempts += 1
                    if review["decision"] == "APPROVE":
                        self._transition(section, SectionStatus.APPROVED)
                    elif section.writing_revision > self.config.limits.max_writing_revisions:
                        self._fail_section(section, "writing revision limit reached")
                        return
                    else:
                        section.last_feedback = review.get("critical_issues", [])
                        self._reset_graph_from(section.id, "write")
                        self._transition(section, SectionStatus.WRITING)
                        self.events.emit("DRAFT_REJECTED", section_id=section.id)
                elif section.status == SectionStatus.APPROVED.value:
                    self._commit_section(section)
                    return
                elif section.status == SectionStatus.COMMITTED.value:
                    return
                elif section.status in {SectionStatus.PAUSED.value, SectionStatus.FAILED.value}:
                    return
                else:
                    raise OrchestrationError(f"unsupported section state: {section.status}")
                save_state(self.store, self.state)
        except ConversationPaused:
            raise
        except AgentExecutionError as exc:
            section.agent_failures += 1
            section.last_error = str(exc)
            if section.agent_failures > self.config.limits.max_agent_failures:
                self._fail_section(section, f"agent failure limit reached: {section.last_error}")
            else:
                save_state(self.store, self.state)
                self.events.emit("AGENT_RETRY_SCHEDULED", section_id=section.id, attempt=section.agent_failures)
        except (SchemaError, OrchestrationError) as exc:
            self._fail_section(section, str(exc))

    def _assemble_and_review(self) -> bool:
        assert self.state is not None and self.events is not None
        set_run_phase(self.state, RunPhase.ASSEMBLY)
        save_state(self.store, self.state)
        sections = list(self.state.sections.values())
        sources = self.store.read_json(".loop/source-index.json")["sources"]
        if self.config.output == "latex":
            _, count = assemble_latex(self.store, sections, sources, self.config.citation_style)
            draft_ref = "output/final-draft.tex"
        else:
            _, count = assemble_markdown(self.store, sections, sources, self.config.citation_style)
            draft_ref = "output/final-draft.md"
        self.events.emit("DOCUMENT_ASSEMBLED", word_count=count)
        set_run_phase(self.state, RunPhase.GLOBAL_REVIEW)
        save_state(self.store, self.state)
        self.events.emit("GLOBAL_REVIEW_STARTED", cycle=self.state.global_review_cycle)
        try:
            value = self._invoke(
                self._task(
                    role="global_reviewer",
                    mode="global_review",
                    input_refs=[draft_ref, "assignment.md", ".loop/global-plan.json", ".loop/source-index.json"],
                    output_ref=".loop/reviews/global-review.json",
                    output_kind="json",
                    instructions="Audit the full assembled document and route any failures to affected section IDs.",
                    metadata={"section_ids": [section.id for section in sections]},
                )
            )
        except AgentExecutionError as exc:
            self.state.agent_failures += 1
            self.state.last_error = str(exc)
            if self.state.agent_failures > self.config.limits.max_agent_failures:
                self._fail_run("global review agent failure limit reached")
                return False
            save_state(self.store, self.state)
            self.events.emit("AGENT_RETRY_SCHEDULED", role="global_reviewer", attempt=self.state.agent_failures)
            return True
        review = validate_global_review(value)
        self.store.write_json(".loop/reviews/global-review.json", review)
        if review["decision"] == "PASS":
            final_ref = "output/final.tex" if self.config.output == "latex" else "output/final.md"
            self.store.write_text(final_ref, self.store.read_text(draft_ref))
            self.state.status = RunStatus.COMPLETED.value
            self.state.current_phase = RunPhase.COMPLETE.value
            self.state.completed_at = utc_now()
            self.state.termination_reason = "global review passed"
            save_state(self.store, self.state)
            self.events.emit("RUN_COMPLETED", output=final_ref, word_count=count)
            return True
        self.state.global_review_cycle += 1
        if self.state.global_review_cycle > self.config.limits.max_global_revisions:
            self._fail_run("global review revision limit reached")
            return False
        affected: dict[str, list[dict[str, Any]]] = {}
        for issue in review.get("issues", []):
            for section_id in issue.get("sections", []):
                if section_id in self.state.sections:
                    affected.setdefault(section_id, []).append(issue)
        if not affected:
            self._fail_run("global review requested revision without affected sections")
            return False
        for section_id, issues in affected.items():
            section = self.state.sections[section_id]
            section.status = SectionStatus.WRITING.value
            section.global_revision_count += 1
            section.affected_by_global_review = True
            section.last_feedback = issues
            self._reset_graph_from(section.id, "write")
            self.events.emit("SECTION_REOPENED", section_id=section_id, reason="global_review")
        save_state(self.store, self.state)
        self.events.emit("GLOBAL_REVIEW_FAILED", cycle=self.state.global_review_cycle, affected=list(affected))
        return True

    def _task(
        self,
        role: str,
        mode: str,
        input_refs: list[str],
        output_ref: str,
        output_kind: str,
        instructions: str,
        section: SectionState | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentTask:
        assert self.state is not None
        role_config = self.config.models.get(role) or self.config.models["reviewer"]
        section_part = f"-{section.id}" if section else ""
        revision_part = ""
        if section:
            revision_part = f"-p{section.plan_revision}-w{section.writing_revision}-g{section.global_revision_count}"
        else:
            revision_part = f"-g{self.state.global_review_cycle}"
        task_id = re.sub(r"[^a-zA-Z0-9_-]", "-", f"{self.state.run_id}-{role}-{mode}{section_part}{revision_part}")
        task_metadata = dict(metadata or {})
        task_metadata["role_contract"] = role_definitions()[role].to_dict()
        if section:
            task_metadata["section"] = {
                "id": section.id,
                "title": section.title,
                "order": section.order,
                "depends_on": section.depends_on,
            }
        return AgentTask(
            task_id=task_id,
            run_id=self.state.run_id,
            role=role,
            mode=mode,
            input_refs=input_refs,
            output_ref=output_ref,
            output_kind=output_kind,
            model=role_config.model,
            effort=role_config.effort,
            timeout_seconds=role_config.timeout_seconds,
            instructions=instructions,
            metadata=task_metadata,
        )

    def _invoke(self, task: AgentTask, section: SectionState | None = None) -> Any:
        assert self.state is not None and self.events is not None
        previous_status = section.status if section else None
        self.state.waiting_for_task = None
        if section:
            section.current_task_id = task.task_id
        save_state(self.store, self.state)
        self.events.emit("AGENT_TASK_STARTED", role=task.role, task_id=task.task_id, section_id=task.metadata.get("section", {}).get("id"))
        result: AgentResult = self.runtime.run(task, self.store)
        if result.status == "waiting":
            if section:
                section.paused_from = previous_status
                section.status = SectionStatus.PAUSED.value
            self.state.status = RunStatus.PAUSED.value
            self.state.waiting_for_task = task.task_id
            save_state(self.store, self.state)
            self.events.emit("AGENT_TASK_WAITING", role=task.role, task_id=task.task_id)
            raise ConversationPaused(result.error or "agent task is waiting")
        if result.status != "completed":
            self.events.emit("AGENT_TASK_FAILED", role=task.role, task_id=task.task_id, error=result.error)
            raise AgentExecutionError(result.error or "agent task failed")
        if task.output_kind == "json":
            if result.output is not None and not self.store.exists(task.output_ref):
                self.store.write_json(task.output_ref, result.output)
        elif task.output_kind == "text":
            if isinstance(result.output, str) and not self.store.exists(task.output_ref):
                self.store.write_text(task.output_ref, result.output)
        self.events.emit("AGENT_TASK_COMPLETED", role=task.role, task_id=task.task_id, section_id=task.metadata.get("section", {}).get("id"))
        if task.task_id in self.state.agent_threads:
            self.state.agent_threads[task.task_id]["status"] = "completed"
        if section:
            section.current_task_id = None
        save_state(self.store, self.state)
        return result.output if result.output is not None else (
            self.store.read_json(task.output_ref) if task.output_kind == "json" else self.store.read_text(task.output_ref)
        )

    def _merge_evidence(self, research: dict[str, Any]) -> None:
        source_ids = {source["id"] for source in self.store.read_json(".loop/source-index.json")["sources"]}
        registry = self.store.read_json(".loop/evidence.json")
        existing = {item["id"] for item in registry.get("evidence", [])}
        for record in research.get("evidence", []):
            if record["source_id"] not in source_ids:
                raise SchemaError(f"evidence references unregistered source: {record['source_id']}")
            if record["id"] not in existing:
                registry.setdefault("evidence", []).append(record)
                existing.add(record["id"])
        self.store.write_json(".loop/evidence.json", registry)

    def _commit_section(self, section: SectionState) -> None:
        assert self.state is not None and self.events is not None
        draft_ref = self._section_ref(section, "draft.md")
        committed_ref = self._section_ref(section, "committed.md")
        self.store.write_text(committed_ref, self.store.read_text(draft_ref))
        section.committed_artifact = committed_ref
        section.affected_by_global_review = False
        self._transition(section, SectionStatus.COMMITTED)
        self.events.emit("SECTION_COMMITTED", section_id=section.id, artifact=committed_ref)

    def _transition(self, section: SectionState, status: SectionStatus) -> None:
        assert self.state is not None and self.events is not None
        section.status = status.value
        self._graph_stage(section.id, status.value)
        save_state(self.store, self.state)
        self.events.emit("SECTION_STATE_CHANGED", section_id=section.id, status=status.value)

    def _fail_section(self, section: SectionState, reason: str) -> None:
        assert self.state is not None and self.events is not None
        section.status = SectionStatus.FAILED.value
        section.last_error = reason
        self.state.status = RunStatus.FAILED.value
        self.state.last_error = f"section {section.id}: {reason}"
        self.state.termination_reason = "section failure"
        save_state(self.store, self.state)
        self.events.emit("SECTION_FAILED", section_id=section.id, error=reason)

    def _fail_run(self, reason: str) -> None:
        assert self.state is not None
        self.state.status = RunStatus.FAILED.value
        self.state.last_error = reason
        self.state.termination_reason = reason
        save_state(self.store, self.state)
        if self.events:
            self.events.emit("RUN_FAILED", error=reason)

    def _section_ref(self, section: SectionState, name: str) -> str:
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "-", section.id)
        return f".loop/sections/{section.order + 1:02d}-{safe_id}/{name}"

    def _section_input_refs(self) -> list[str]:
        refs = ["assignment.md"]
        if self.store.exists(".loop/request.md"):
            refs.append(".loop/request.md")
        refs.extend([".loop/global-plan.json", ".loop/source-index.json"])
        return refs

    def _graph_stage(self, section_id: str, status: str) -> None:
        mapping = {
            SectionStatus.PLAN_REVIEW.value: "plan",
            SectionStatus.RESEARCHING.value: "plan_review",
            SectionStatus.WRITING.value: "research",
            SectionStatus.WRITING_REVIEW.value: "write",
            SectionStatus.APPROVED.value: "writing_review",
            SectionStatus.COMMITTED.value: "commit",
        }
        if status not in mapping:
            return
        self._set_graph_status(f"{section_id}:{mapping[status]}", "completed")

    def _reset_graph_from(self, section_id: str, stage: str) -> None:
        assert self.state is not None
        graph = TaskGraph.from_dict(self.state.graph)
        stages = ["plan", "plan_review", "research", "write", "writing_review", "commit"]
        for candidate in stages[stages.index(stage) :]:
            graph.set_status(f"{section_id}:{candidate}", "pending")
        self.state.graph = graph.to_dict()
        self._persist_graph()

    def _set_graph_status(self, node_id: str, status: str) -> None:
        assert self.state is not None
        graph = TaskGraph.from_dict(self.state.graph)
        graph.set_status(node_id, status)
        self.state.graph = graph.to_dict()
        self._persist_graph()

    def _persist_graph(self) -> None:
        assert self.state is not None
        self.store.write_json(".loop/task-graph.json", self.state.graph)

    def _restore_paused_sections(self) -> None:
        assert self.state is not None
        for section in self.state.sections.values():
            if section.status == SectionStatus.PAUSED.value:
                section.status = section.paused_from or SectionStatus.PENDING.value
                section.paused_from = None
        save_state(self.store, self.state)

    def _waiting_message(self) -> str:
        assert self.state is not None
        if self.state.waiting_for_task:
            return f"waiting for Codex task {self.state.waiting_for_task}"
        return "run paused"

    def _terminal_message(self) -> str:
        assert self.state is not None
        return self.state.termination_reason or self.state.status

    def _status_message(self) -> str:
        assert self.state is not None
        if self.state.status == RunStatus.PAUSED.value:
            return self._waiting_message()
        if self.state.status == RunStatus.FAILED.value:
            return self.state.last_error or "run failed"
        if self.state.status == RunStatus.COMPLETED.value:
            return "global review passed and final output was generated"
        return f"run {self.state.status}"
