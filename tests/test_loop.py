from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
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


def add_required_sources(root: Path, links: str = "[Example source](https://example.com/source)\n") -> Path:
    sources = root / "sources"
    sources.mkdir()
    (sources / "links.md").write_text(links, encoding="utf-8")
    return sources


class LoopFoundationTests(unittest.TestCase):
    def test_init_creates_canonical_workspace_and_starter_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            class_root = Path(temp)
            root = class_root / "CISC335"
            output = io.StringIO()
            previous_cwd = Path.cwd()
            try:
                os.chdir(class_root)
                with redirect_stdout(output):
                    self.assertEqual(main(["init", "CISC335", "--json"]), 0)
            finally:
                os.chdir(previous_cwd)

            result = json.loads(output.getvalue())
            self.assertEqual(result["root"], str(root))
            for relative in (
                "outline",
                "sources",
                ".loop",
                ".loop/sections",
                ".loop/reviews",
                ".loop/logs",
                ".loop/tasks",
                ".loop/agent-results",
                "output",
            ):
                self.assertTrue((root / relative).is_dir(), relative)

            assignment = root / "assignment.md"
            links = root / "sources" / "links.md"
            readme = root / "README.md"
            self.assertTrue(assignment.is_file())
            self.assertTrue(links.is_file())
            self.assertTrue(readme.is_file())
            self.assertIn("Describe the task to complete.", assignment.read_text(encoding="utf-8"))
            self.assertIn("HTTP(S)", links.read_text(encoding="utf-8"))
            self.assertIn("loop run .", readme.read_text(encoding="utf-8"))
            self.assertTrue(result["created"])
            self.assertFalse(result["existing"])

    def test_init_is_idempotent_and_preserves_existing_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            class_root = Path(temp)
            root = class_root / "CISC335"
            previous_cwd = Path.cwd()
            try:
                os.chdir(class_root)
                self.assertEqual(main(["init", "CISC335"]), 0)
            finally:
                os.chdir(previous_cwd)
            assignment = root / "assignment.md"
            links = root / "sources" / "links.md"
            readme = root / "README.md"
            assignment.write_text("# My assignment\n", encoding="utf-8")
            links.write_text("https://example.com/my-source\n", encoding="utf-8")
            readme.write_text("# My notes\n", encoding="utf-8")

            output = io.StringIO()
            try:
                os.chdir(class_root)
                with redirect_stdout(output):
                    self.assertEqual(main(["init", "CISC335", "--json"]), 0)
            finally:
                os.chdir(previous_cwd)

            result = json.loads(output.getvalue())
            self.assertFalse(result["created"])
            self.assertIn("assignment.md", result["existing"])
            self.assertIn("sources/links.md", result["existing"])
            self.assertIn("README.md", result["existing"])
            self.assertEqual(assignment.read_text(encoding="utf-8"), "# My assignment\n")
            self.assertEqual(links.read_text(encoding="utf-8"), "https://example.com/my-source\n")
            self.assertEqual(readme.read_text(encoding="utf-8"), "# My notes\n")

    def test_init_rejects_a_path_as_the_assignment_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            class_root = Path(temp)
            previous_cwd = Path.cwd()
            try:
                os.chdir(class_root)
                self.assertEqual(main(["init", "nested/CISC335"]), 2)
            finally:
                os.chdir(previous_cwd)
            self.assertFalse((class_root / "nested").exists())

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
            add_required_sources(root)

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
            add_required_sources(root)

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
            sources = add_required_sources(root)
            (sources / "past-grade.pdf").write_bytes(b"%PDF-1.4\n")

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
            self.assertIn("sources/links.md", task["input_refs"])
            self.assertIn("sources/past-grade.pdf", task["input_refs"])
            self.assertIn("past-mark", task["instructions"])
            self.assertIn("do/not-do", task["instructions"])
            self.assertIn("web search", task["instructions"].lower())
            self.assertEqual(task["metadata"]["outline_guidance"]["past_marks_files"], ["outline/lost-marks.md"])
            self.assertEqual(task["metadata"]["source_guidance"]["feedback_files"], ["sources/past-grade.pdf"])
            self.assertTrue(task["metadata"]["source_guidance"]["web_search_enabled"])
            self.assertTrue((root / ".loop" / "outline-index.json").exists())

    def test_sources_require_links_and_index_only_external_links(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "assignment.md").write_text("Complete the assignment.", encoding="utf-8")
            sources = add_required_sources(
                root,
                "# Sources\n\n[First source](https://example.com/first)\n"
                "Second source: https://example.org/second.\n"
                "Duplicate: https://example.com/first\n",
            )
            (sources / "past-grade.pdf").write_bytes(b"%PDF-1.4\n")
            (sources / "professor-feedback.docx").write_bytes(b"PK\x03\x04")
            (sources / "previous-comments.txt").write_text("Lost marks for weak analysis.", encoding="utf-8")

            workspace = Workspace.discover(root)
            manifest = workspace.input_manifest()
            registry = workspace.source_index()

            self.assertEqual(manifest["links_file"], "sources/links.md")
            self.assertEqual(manifest["source_files"], ["sources/links.md"])
            self.assertEqual(
                manifest["source_feedback_files"],
                [
                    "sources/past-grade.pdf",
                    "sources/previous-comments.txt",
                    "sources/professor-feedback.docx",
                ],
            )
            self.assertEqual([item["id"] for item in registry], ["S01", "S02"])
            self.assertEqual(registry[0]["title"], "First source")
            self.assertEqual(registry[0]["type"], "web")
            self.assertEqual(registry[0]["url"], "https://example.com/first")
            self.assertEqual(registry[1]["url"], "https://example.org/second")
            self.assertTrue(all(item["path"] == "sources/links.md" for item in registry))

    def test_sources_links_md_is_required_and_other_types_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "assignment.md").write_text("Complete the assignment.", encoding="utf-8")
            (root / "sources").mkdir()

            with self.assertRaisesRegex(WorkspaceError, "sources/links.md is required"):
                Workspace.discover(root).input_manifest()

            (root / "sources" / "links.md").write_text("https://example.com", encoding="utf-8")
            (root / "sources" / "notes.png").write_bytes(b"not an allowed feedback format")
            with self.assertRaisesRegex(WorkspaceError, "unsupported file"):
                Workspace.discover(root).input_manifest()

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
            add_required_sources(root)
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
            add_required_sources(root)
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
            add_required_sources(root)
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
