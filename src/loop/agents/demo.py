"""A deterministic local runtime used for smoke tests and first-run demonstrations.

It intentionally produces modest, clearly synthetic content. It proves the workflow
backbone without pretending that local code is a substitute for a reasoning model.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..schemas import (
    validate_global_plan,
    validate_global_review,
    validate_plan_review,
    validate_research,
    validate_section_plan,
    validate_writing_review,
)
from .contracts import AgentResult, AgentRuntime, AgentTask


def _slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value or "section"


def _unique_slug(value: str, seen: set[str]) -> str:
    base = _slug(value)
    candidate = base
    counter = 2
    while candidate in seen:
        candidate = f"{base}-{counter}"
        counter += 1
    seen.add(candidate)
    return candidate


def _heading_lines(text: str) -> list[str]:
    headings: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^#{1,3}\s+(.+?)\s*$", line)
        if match:
            title = re.sub(r"^\d+[.)]\s*", "", match.group(1)).strip()
            if title and title.lower() not in {"outline", "contents"}:
                headings.append(title)
    return headings


class DemoAgentRuntime(AgentRuntime):
    """Run each role deterministically from persisted artifact references."""

    name = "demo"

    def run(self, task: AgentTask, store: Any) -> AgentResult:
        try:
            output = self._dispatch(task, store)
            return AgentResult(status="completed", output=output)
        except Exception as exc:  # runtime converts malformed role output into a bounded failure
            return AgentResult(status="failed", error=f"demo agent failed: {exc}")

    def _read(self, store: Any, relative: str) -> str:
        return store.read_text(relative)

    def _json(self, store: Any, relative: str) -> Any:
        return store.read_json(relative)

    def _dispatch(self, task: AgentTask, store: Any) -> Any:
        if task.role == "orchestrator":
            return self._global_plan(task, store)
        if task.role == "planner":
            return self._section_plan(task, store)
        if task.role == "reviewer" and task.mode == "plan_review":
            return self._plan_review(task, store)
        if task.role == "researcher":
            return self._research(task, store)
        if task.role == "writer":
            return self._write(task, store)
        if task.role == "reviewer" and task.mode == "writing_review":
            return self._writing_review(task, store)
        if task.role == "global_reviewer":
            return self._global_review(task, store)
        raise ValueError(f"demo runtime does not support {task.role}/{task.mode}")

    def _global_plan(self, task: AgentTask, store: Any) -> dict[str, Any]:
        assignment = self._read(store, task.input_refs[0])
        outline = ""
        for ref in task.input_refs[1:]:
            if ref.endswith("outline.md") and store.exists(ref):
                outline = self._read(store, ref)
        titles = _heading_lines(outline)
        if not titles:
            titles = ["Introduction", "Analysis", "Conclusion"]
        seen: set[str] = set()
        total_target = 900
        target = max(200, total_target // len(titles))
        sections = []
        for index, title in enumerate(titles):
            section_id = _unique_slug(title, seen)
            sections.append(
                {
                    "id": section_id,
                    "title": title,
                    "order": index,
                    "objective": f"Develop the assignment's {title.lower()} section.",
                    "target_words": target,
                    "depends_on": [],
                }
            )
        summary = re.sub(r"\s+", " ", assignment).strip()[:500]
        return validate_global_plan({"summary": summary or "Assignment", "sections": sections})

    def _section_context(self, task: AgentTask, store: Any) -> dict[str, Any]:
        context = task.metadata.get("section")
        if not isinstance(context, dict):
            raise ValueError("task metadata.section is required")
        return context

    def _section_plan(self, task: AgentTask, store: Any) -> dict[str, Any]:
        section = self._section_context(task, store)
        section_id = section["id"]
        plan = {
            "section_id": section_id,
            "objective": section.get("objective") or f"Develop {section['title']}.",
            "target_words": max(100, int(section.get("target_words", 300))),
            "claims": [
                {
                    "id": f"{section_id}-C1",
                    "statement": f"{section['title']} advances the assignment's central response.",
                    "evidence_required": ["source-backed explanation"],
                },
                {
                    "id": f"{section_id}-C2",
                    "statement": f"The evidence can be interpreted in relation to the assignment requirements.",
                    "evidence_required": ["source-backed analysis"],
                },
            ],
            "structure": ["opening claim", "evidence and explanation", "section synthesis"],
            "dependencies": section.get("depends_on", []),
        }
        return validate_section_plan(plan)

    def _plan_review(self, task: AgentTask, store: Any) -> dict[str, Any]:
        plan = self._json(store, task.input_refs[0])
        if plan.get("claims") and plan.get("structure"):
            return validate_plan_review(
                {"decision": "APPROVE", "issues": [], "missing_evidence": [], "scope_issues": []}
            )
        return validate_plan_review(
            {
                "decision": "REVISE",
                "issues": [{"type": "INCOMPLETE_PLAN", "description": "Add claims and structure."}],
                "missing_evidence": [],
                "scope_issues": [],
            }
        )

    def _research(self, task: AgentTask, store: Any) -> dict[str, Any]:
        section = self._section_context(task, store)
        plan = self._json(store, task.input_refs[0])
        source_index = self._json(store, " .loop/source-index.json".strip())
        source_index = source_index.get("sources", source_index)
        evidence: list[dict[str, Any]] = []
        claims: list[dict[str, Any]] = []
        for claim in plan["claims"]:
            linked: list[str] = []
            if source_index:
                source = source_index[len(evidence) % len(source_index)]
                evidence_id = f"{source['id']}-E{len(evidence) + 1:02d}"
                source_text = ""
                if source.get("path") and store.exists(source["path"]):
                    try:
                        source_text = re.sub(r"\s+", " ", store.read_text(source["path"])).strip()
                    except UnicodeDecodeError:
                        source_text = ""
                paraphrase = (source_text[:240] if source_text else f"Evidence relevant to {claim['statement']}")
                evidence.append(
                    {
                        "id": evidence_id,
                        "source_id": source["id"],
                        "supports": [f"{section['id']}:{claim['id']}"],
                        "location": "source file",
                        "paraphrase": paraphrase,
                        "confidence": "medium" if source_text else "low",
                    }
                )
                linked.append(evidence_id)
            claims.append({"claim_id": claim["id"], "evidence": linked})
        return validate_research({"section_id": section["id"], "claims": claims, "evidence": evidence})

    def _write(self, task: AgentTask, store: Any) -> str:
        section = self._section_context(task, store)
        plan = self._json(store, task.input_refs[0])
        research = self._json(store, task.input_refs[1])
        evidence_by_id = {
            item["id"]: item for item in self._json(store, ".loop/evidence.json").get("evidence", [])
        }
        paragraphs = [
            f"{plan['objective']} This section establishes the role of {section['title'].lower()} within the assignment."
        ]
        for claim, research_claim in zip(plan["claims"], research["claims"]):
            markers = " ".join(
                f"[{evidence_by_id[evidence_id]['source_id']}]"
                for evidence_id in research_claim.get("evidence", [])
                if evidence_id in evidence_by_id
            )
            paragraphs.append(f"{claim['statement']} {markers}".strip())
        paragraphs.append("Taken together, these points connect the section back to the assignment requirements.")
        return "\n\n".join(paragraphs) + "\n"

    def _writing_review(self, task: AgentTask, store: Any) -> dict[str, Any]:
        draft = self._read(store, task.input_refs[0])
        markers = re.findall(r"\[(S\d+)\]", draft)
        source_ids = {
            item["id"] for item in self._json(store, ".loop/source-index.json").get("sources", [])
        }
        invalid = sorted(set(markers) - source_ids)
        if draft.strip() and not invalid:
            return validate_writing_review(
                {
                    "decision": "APPROVE",
                    "score": 85,
                    "critical_issues": [],
                    "citation_issues": [],
                    "formatting_issues": [],
                    "argument_issues": [],
                }
            )
        issues = []
        if not draft.strip():
            issues.append({"type": "EMPTY_DRAFT", "description": "Draft is empty."})
        if invalid:
            issues.append({"type": "UNKNOWN_SOURCE", "description": f"Unknown sources: {invalid}"})
        return validate_writing_review(
            {
                "decision": "REVISE",
                "score": 0,
                "critical_issues": issues,
                "citation_issues": [],
                "formatting_issues": [],
                "argument_issues": [],
            }
        )

    def _global_review(self, task: AgentTask, store: Any) -> dict[str, Any]:
        draft = self._read(store, task.input_refs[0])
        sections = task.metadata.get("section_ids", [])
        issues = []
        if not draft.strip():
            issues.append(
                {
                    "type": "EMPTY_DOCUMENT",
                    "sections": list(sections),
                    "description": "The assembled document is empty.",
                }
            )
        for section_id in sections:
            if f"## {section_id}" not in draft and not any(
                line.startswith("## ") and _slug(line[3:]) == section_id for line in draft.splitlines()
            ):
                issues.append(
                    {
                        "type": "MISSING_SECTION",
                        "sections": [section_id],
                        "description": f"Section {section_id} is missing from the assembled document.",
                    }
                )
        return validate_global_review({"decision": "PASS" if not issues else "REVISE", "issues": issues})
