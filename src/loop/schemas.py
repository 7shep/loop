"""Runtime validation for the structured agent contracts."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


class SchemaError(ValueError):
    """Raised when an agent result cannot safely enter persisted state."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaError(f"{label} must be an object")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f"{label} must be a non-empty string")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise SchemaError(f"{label} must be an array")
    return value


def _decision(value: Any, allowed: Iterable[str], label: str = "decision") -> str:
    normalized = str(value).upper()
    if normalized not in set(allowed):
        raise SchemaError(f"{label} must be one of {sorted(set(allowed))}")
    return normalized


def validate_global_plan(value: Any) -> dict[str, Any]:
    plan = _object(value, "global plan")
    _string(plan.get("summary"), "global plan.summary")
    sections = _list(plan.get("sections"), "global plan.sections")
    if not sections:
        raise SchemaError("global plan.sections cannot be empty")
    ids: set[str] = set()
    for index, section in enumerate(sections):
        item = _object(section, f"global plan.sections[{index}]")
        section_id = _string(item.get("id"), f"global plan.sections[{index}].id")
        if section_id in ids:
            raise SchemaError(f"duplicate section id: {section_id}")
        ids.add(section_id)
        _string(item.get("title"), f"global plan.sections[{index}].title")
        if not isinstance(item.get("order"), int):
            raise SchemaError(f"global plan.sections[{index}].order must be an integer")
        if not isinstance(item.get("depends_on", []), list):
            raise SchemaError(f"global plan.sections[{index}].depends_on must be an array")
    for section in sections:
        for dependency in section.get("depends_on", []):
            if dependency not in ids:
                raise SchemaError(f"section {section['id']} depends on unknown section {dependency}")
            if dependency == section["id"]:
                raise SchemaError(f"section {section['id']} cannot depend on itself")
    return plan


def validate_section_plan(value: Any) -> dict[str, Any]:
    plan = _object(value, "section plan")
    _string(plan.get("section_id"), "section plan.section_id")
    _string(plan.get("objective"), "section plan.objective")
    if not isinstance(plan.get("target_words"), int) or plan["target_words"] <= 0:
        raise SchemaError("section plan.target_words must be a positive integer")
    claims = _list(plan.get("claims"), "section plan.claims")
    if not claims:
        raise SchemaError("section plan.claims cannot be empty")
    for index, claim in enumerate(claims):
        item = _object(claim, f"section plan.claims[{index}]")
        _string(item.get("id"), f"section plan.claims[{index}].id")
        _string(item.get("statement"), f"section plan.claims[{index}].statement")
        if not isinstance(item.get("evidence_required", []), list):
            raise SchemaError(f"section plan.claims[{index}].evidence_required must be an array")
    structure = _list(plan.get("structure"), "section plan.structure")
    if not structure or not all(isinstance(item, str) and item.strip() for item in structure):
        raise SchemaError("section plan.structure must contain at least one non-empty string")
    return plan


def validate_plan_review(value: Any) -> dict[str, Any]:
    review = _object(value, "plan review")
    review["decision"] = _decision(review.get("decision"), {"APPROVE", "REVISE"})
    review.setdefault("issues", [])
    review.setdefault("missing_evidence", [])
    review.setdefault("scope_issues", [])
    for key in ("issues", "missing_evidence", "scope_issues"):
        _list(review[key], f"plan review.{key}")
    return review


def validate_research(value: Any) -> dict[str, Any]:
    research = _object(value, "research")
    _string(research.get("section_id"), "research.section_id")
    claims = _list(research.get("claims"), "research.claims")
    for index, claim in enumerate(claims):
        item = _object(claim, f"research.claims[{index}]")
        _string(item.get("claim_id"), f"research.claims[{index}].claim_id")
        if not isinstance(item.get("evidence", []), list):
            raise SchemaError(f"research.claims[{index}].evidence must be an array")
    evidence = _list(research.get("evidence", []), "research.evidence")
    for index, record in enumerate(evidence):
        item = _object(record, f"research.evidence[{index}]")
        for key in ("id", "source_id", "location", "paraphrase", "confidence"):
            _string(item.get(key), f"research.evidence[{index}].{key}")
        if not isinstance(item.get("supports", []), list):
            raise SchemaError(f"research.evidence[{index}].supports must be an array")
    return research


def validate_writing_review(value: Any) -> dict[str, Any]:
    review = _object(value, "writing review")
    review["decision"] = _decision(review.get("decision"), {"APPROVE", "REVISE"})
    if "score" in review and (not isinstance(review["score"], (int, float)) or not 0 <= review["score"] <= 100):
        raise SchemaError("writing review.score must be between 0 and 100")
    for key in ("critical_issues", "citation_issues", "formatting_issues", "argument_issues"):
        review.setdefault(key, [])
        _list(review[key], f"writing review.{key}")
    return review


def validate_global_review(value: Any) -> dict[str, Any]:
    review = _object(value, "global review")
    review["decision"] = _decision(review.get("decision"), {"PASS", "REVISE"})
    issues = _list(review.get("issues", []), "global review.issues")
    review["issues"] = issues
    for index, issue in enumerate(issues):
        item = _object(issue, f"global review.issues[{index}]")
        _string(item.get("type"), f"global review.issues[{index}].type")
        _string(item.get("description"), f"global review.issues[{index}].description")
        if not isinstance(item.get("sections", []), list):
            raise SchemaError(f"global review.issues[{index}].sections must be an array")
    return review
