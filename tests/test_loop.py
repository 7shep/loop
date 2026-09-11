from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from loop.agents.demo import DemoAgentRuntime
from loop.agents.conversation import ConversationAgentRuntime
from loop.agents.contracts import AgentResult
from loop.cli import main
from loop.config import LoopConfig
from loop.graph import GraphError, TaskGraph
from loop.orchestrator import LoopOrchestrator
from loop.workspace import Workspace, WorkspaceError


class ReopenOnceRuntime(DemoAgentRuntime):
    def __init__(self) -> None:
        self.reopened = False

    def run(self, task, store):
        if task.role == "global_reviewer" and not self.reopened:
            self.reopened = True
            return AgentResult(
                status="completed",
                output={
                    "decision": "REVISE",
                    "issues": [
                        {
                            "type": "ARGUMENT_GAP",
                            "sections": ["background"],
                            "description": "Strengthen the opening section's link to the thesis.",
                        }
                    ],
                },
            )
        return super().run(task, store)


class LoopFoundationTests(unittest.TestCase):
    def test_graph_rejects_cycles(self) -> None:
        with self.assertRaises(GraphError):
            TaskGraph.from_dict(
                {
                    "nodes": [
                        {"id": "a", "depends_on": ["b"]},
                        {"id": "b", "depends_on": ["a"]},
                    ]
                }
            )

    def test_workspace_does_not_resolve_outside_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Workspace.discover(temp)
            with self.assertRaises(WorkspaceError):
                workspace.inside(Path(temp).parent)

    def test_outline_folder_indexes_pdf_and_history_without_fixed_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "assignment.md").write_text("Complete the assignment.", encoding="utf-8")
            outline = root / "outline"
            outline.mkdir()
            (outline / "brief.pdf").write_bytes(b"%PDF-1.4\n")
            (outline / "grading-criteria.pdf").write_bytes(b"%PDF-1.4\n")
            (outline / "prior-feedback.pdf").write_bytes(b"%PDF-1.4\n")
            (outline / "rubric-feedback.pdf").write_bytes(b"%PDF-1.4\n")
            (outline / "class-notes.txt").write_text("Additional guidance.", encoding="utf-8")

            manifest = Workspace.discover(root).input_manifest()

            self.assertEqual(
                manifest["outline_files"],
                [
                    "outline/brief.pdf",
                    "outline/class-notes.txt",
                    "outline/grading-criteria.pdf",
                    "outline/prior-feedback.pdf",
                    "outline/rubric-feedback.pdf",
                ],
            )
            self.assertEqual(manifest["assignment_outline_files"], ["outline/brief.pdf"])
            self.assertEqual(
                manifest["rubric_files"],
                ["outline/grading-criteria.pdf", "outline/rubric-feedback.pdf"],
            )
            self.assertEqual(
                manifest["past_marks_files"],
                ["outline/prior-feedback.pdf", "outline/rubric-feedback.pdf"],
            )
            self.assertEqual(manifest["other_guidance_files"], ["outline/class-notes.txt"])

    def test_legacy_root_outline_inputs_remain_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "assignment.md").write_text("Complete the assignment.", encoding="utf-8")
            (root / "outline.md").write_text("# Introduction", encoding="utf-8")
            (root / "rubric.pdf").write_bytes(b"%PDF-1.4\n")

            manifest = Workspace.discover(root).input_manifest()

            self.assertEqual(manifest["outline_files"], ["outline.md", "rubric.pdf"])
            self.assertEqual(manifest["outline_file"], "outline.md")
            self.assertEqual(manifest["rubric_file"], "rubric.pdf")
            self.assertEqual(manifest["legacy_outline_files"], ["outline.md", "rubric.pdf"])

    def test_conversation_task_contains_outline_and_past_mark_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "assignment.md").write_text("Complete the assignment.", encoding="utf-8")
            outline = root / "outline"
            outline.mkdir()
            (outline / "assignment-brief.pdf").write_bytes(b"%PDF-1.4\n")
            (outline / "lost-marks.md").write_text(
                "Past feedback: insufficient evidence.", encoding="utf-8"
            )

            orchestrator = LoopOrchestrator(
                Workspace.discover(root),
                config=LoopConfig(runtime="conversation"),
                runtime=ConversationAgentRuntime(),
            )
            result = orchestrator.run()
            self.assertEqual(result.status, "paused")

            state = json.loads((root / ".loop" / "state.json").read_text(encoding="utf-8"))
            task_id = state["waiting_for_task"]
            task = json.loads(
                (root / ".loop" / "tasks" / f"{task_id}.json").read_text(encoding="utf-8")
            )
            self.assertIn("outline/assignment-brief.pdf", task["input_refs"])
            self.assertIn("outline/lost-marks.md", task["input_refs"])
            self.assertIn("past-mark", task["instructions"])
            self.assertIn("do/not-do", task["instructions"])
            self.assertEqual(task["metadata"]["outline_guidance"]["past_marks_files"], ["outline/lost-marks.md"])
            self.assertTrue((root / ".loop" / "outline-index.json").exists())

    def test_demo_runtime_completes_full_review_gated_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "assignment.md").write_text(
                "Explain the significance of the supplied evidence.", encoding="utf-8"
            )
            (root / "outline").mkdir()
            (root / "outline" / "assignment-outline.md").write_text(
                "# Background\n# Analysis\n# Conclusion\n", encoding="utf-8"
            )
            (root / "sources").mkdir()
            (root / "sources" / "source-01.md").write_text(
                "A supplied source statement for the assignment.", encoding="utf-8"
            )
            config = LoopConfig(runtime="demo")
            orchestrator = LoopOrchestrator(
                Workspace.discover(root),
                config=config,
                runtime=DemoAgentRuntime(),
                request="Complete this assignment using the supplied sources.",
            )
            result = orchestrator.run()

            self.assertEqual(result.status, "completed", result.message)
            self.assertTrue((root / "output" / "final.md").exists())
            self.assertTrue((root / ".loop" / "reviews" / "global-review.json").exists())
            state = json.loads((root / ".loop" / "state.json").read_text(encoding="utf-8"))
            self.assertTrue(all(item["status"] == "committed" for item in state["sections"].values()))
            review = json.loads(
                (root / ".loop" / "reviews" / "global-review.json").read_text(encoding="utf-8")
            )
            self.assertEqual(review["decision"], "PASS")
            self.assertIn("References", (root / "output" / "final.md").read_text(encoding="utf-8"))
            self.assertTrue((root / ".loop" / "request.md").exists())

    def test_conversation_runtime_persists_a_resumable_task_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "assignment.md").write_text("Complete the assignment.", encoding="utf-8")
            workspace = Workspace.discover(root)
            orchestrator = LoopOrchestrator(
                workspace, config=LoopConfig(runtime="conversation"), runtime=ConversationAgentRuntime()
            )
            first = orchestrator.run()
            self.assertEqual(first.status, "paused")
            task_id = json.loads((root / ".loop" / "state.json").read_text(encoding="utf-8"))["waiting_for_task"]
            manifest_path = root / ".loop" / "tasks" / f"{task_id}.json"
            self.assertEqual(main(["task-bind", str(root), "--task-id", task_id, "--thread-id", "thread-123"]), 0)
            bound_state = json.loads((root / ".loop" / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(bound_state["agent_threads"][task_id]["thread_id"], "thread-123")
            (root / ".loop" / "global-plan.json").write_text(
                json.dumps(
                    {
                        "summary": "A simple assignment",
                        "sections": [
                            {
                                "id": "introduction",
                                "title": "Introduction",
                                "order": 0,
                                "depends_on": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            ConversationAgentRuntime.complete_task(task_id, orchestrator.store)
            resumed = orchestrator.run(resume=True)
            self.assertEqual(resumed.status, "paused")
            pending = list((root / ".loop" / "tasks").glob("*.json"))
            self.assertTrue(any(json.loads(path.read_text(encoding="utf-8"))["role"] == "planner" for path in pending))

    def test_global_review_reopens_only_affected_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "assignment.md").write_text("Compare the two sections.", encoding="utf-8")
            (root / "outline").mkdir()
            (root / "outline" / "assignment-outline.md").write_text(
                "# Background\n# Analysis\n", encoding="utf-8"
            )
            runtime = ReopenOnceRuntime()
            orchestrator = LoopOrchestrator(
                Workspace.discover(root), config=LoopConfig(runtime="demo"), runtime=runtime
            )
            result = orchestrator.run()

            self.assertEqual(result.status, "completed", result.message)
            state = json.loads((root / ".loop" / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["global_review_cycle"], 1)
            self.assertEqual(state["sections"]["background"]["global_revision_count"], 1)
            self.assertEqual(state["sections"]["analysis"]["global_revision_count"], 0)


if __name__ == "__main__":
    unittest.main()
