"""Dependency-aware task graph used by the deterministic orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class GraphError(ValueError):
    pass


@dataclass
class TaskNode:
    id: str
    kind: str
    section_id: str | None
    stage: str
    depends_on: list[str] = field(default_factory=list)
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "section_id": self.section_id,
            "stage": self.stage,
            "depends_on": list(self.depends_on),
            "status": self.status,
        }


class TaskGraph:
    def __init__(self, nodes: dict[str, TaskNode] | None = None):
        self.nodes = nodes or {}
        self.validate()

    @classmethod
    def from_global_plan(cls, plan: dict[str, Any]) -> "TaskGraph":
        nodes: dict[str, TaskNode] = {}
        for section in sorted(plan["sections"], key=lambda item: item["order"]):
            section_id = section["id"]
            dependency_commits = [f"{dependency}:commit" for dependency in section.get("depends_on", [])]
            stages = ["plan", "plan_review", "research", "write", "writing_review", "commit"]
            for index, stage in enumerate(stages):
                node_id = f"{section_id}:{stage}"
                dependencies = list(dependency_commits) if index == 0 else [f"{section_id}:{stages[index - 1]}"]
                nodes[node_id] = TaskNode(
                    id=node_id,
                    kind="section_stage",
                    section_id=section_id,
                    stage=stage,
                    depends_on=dependencies,
                )
        return cls(nodes)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TaskGraph":
        raw_nodes = value.get("nodes", [])
        nodes = {
            item["id"]: TaskNode(
                id=item["id"],
                kind=item.get("kind", "section_stage"),
                section_id=item.get("section_id"),
                stage=item.get("stage", "unknown"),
                depends_on=list(item.get("depends_on", [])),
                status=item.get("status", "pending"),
            )
            for item in raw_nodes
        }
        return cls(nodes)

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": [node.to_dict() for node in self.nodes.values()]}

    def validate(self) -> None:
        for node in self.nodes.values():
            for dependency in node.depends_on:
                if dependency not in self.nodes:
                    raise GraphError(f"task {node.id} depends on unknown task {dependency}")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise GraphError(f"task graph contains a cycle at {node_id}")
            if node_id in visited:
                return
            visiting.add(node_id)
            for dependency in self.nodes[node_id].depends_on:
                visit(dependency)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in self.nodes:
            visit(node_id)

    def ready(self, completed: set[str] | None = None) -> list[TaskNode]:
        completed_ids = completed or {node.id for node in self.nodes.values() if node.status == "completed"}
        return [
            node
            for node in self.nodes.values()
            if node.status == "pending" and all(dependency in completed_ids for dependency in node.depends_on)
        ]

    def set_status(self, node_id: str, status: str) -> None:
        if node_id not in self.nodes:
            raise GraphError(f"unknown task: {node_id}")
        self.nodes[node_id].status = status

    def section_ready(self, section_id: str, completed_sections: set[str]) -> bool:
        node_ids = [node.id for node in self.nodes.values() if node.section_id == section_id]
        if not node_ids:
            raise GraphError(f"unknown section: {section_id}")
        first = self.nodes[f"{section_id}:plan"]
        return all(dependency.split(":", 1)[0] in completed_sections for dependency in first.depends_on)
