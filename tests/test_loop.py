from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from loop.agents.demo import DemoAgentRuntime
from loop.config import LoopConfig
from loop.graph import GraphError, TaskGraph
from loop.orchestrator import LoopOrchestrator
from loop.workspace import Workspace, WorkspaceError


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

    def test_demo_runtime_completes_full_review_gated_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "assignment.md").write_text(
                "Explain the significance of the supplied evidence.", encoding="utf-8"
            )
            (root / "outline.md").write_text(
                "# Background\n# Analysis\n# Conclusion\n", encoding="utf-8"
            )
            (root / "sources").mkdir()
            (root / "sources" / "source-01.md").write_text(
                "A supplied source statement for the assignment.", encoding="utf-8"
            )
            config = LoopConfig(runtime="demo")
            orchestrator = LoopOrchestrator(
                Workspace.discover(root), config=config, runtime=DemoAgentRuntime()
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


if __name__ == "__main__":
    unittest.main()
