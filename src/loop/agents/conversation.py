"""Queue-backed Codex/ChatGPT conversation runtime.

The local package cannot assume an API key or a particular Codex SDK. Instead it
materialises a least-privilege task manifest. The active Codex/Work conversation
fulfils that manifest, writes the declared artifact, and marks it complete. A
subsequent resume consumes the result. This keeps one visible conversation while
leaving provider-specific thread creation to the host integration.
"""

from __future__ import annotations

from typing import Any

from .contracts import AgentResult, AgentRuntime, AgentTask


class ConversationAgentRuntime(AgentRuntime):
    name = "conversation"

    def run(self, task: AgentTask, store: Any) -> AgentResult:
        manifest_ref = f".loop/tasks/{task.task_id}.json"
        result_ref = f".loop/agent-results/{task.task_id}.json"
        if store.exists(result_ref):
            result = store.read_json(result_ref)
            if result.get("status") != "completed":
                return AgentResult(status="failed", error=result.get("error", "task failed"))
            if task.output_kind == "text":
                if not store.exists(task.output_ref):
                    return AgentResult(status="failed", error="task completion marker has no output artifact")
                return AgentResult(status="completed", output=store.read_text(task.output_ref))
            if not store.exists(task.output_ref):
                return AgentResult(status="failed", error="task completion marker has no output artifact")
            return AgentResult(status="completed", output=store.read_json(task.output_ref))

        if not store.exists(manifest_ref):
            store.path(task.output_ref).parent.mkdir(parents=True, exist_ok=True)
            store.write_json(manifest_ref, task.to_dict())
        return AgentResult(
            status="waiting",
            error=(
                f"Codex task queued at {manifest_ref}; complete it in the active conversation "
                f"and mark it with `loop task-complete . --task-id {task.task_id}`."
            ),
        )

    @staticmethod
    def complete_task(task_id: str, store: Any) -> str:
        manifest_ref = f".loop/tasks/{task_id}.json"
        if not store.exists(manifest_ref):
            raise ValueError(f"unknown task: {task_id}")
        task = store.read_json(manifest_ref)
        output_ref = task.get("output_ref")
        if not output_ref or not store.exists(output_ref):
            raise ValueError(f"task output is missing: {output_ref}")
        result_ref = f".loop/agent-results/{task_id}.json"
        store.write_json(result_ref, {"task_id": task_id, "status": "completed"})
        return result_ref
