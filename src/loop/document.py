"""Deterministic document assembly and citation normalization."""

from __future__ import annotations

import re
from typing import Any

from .artifacts.store import ArtifactStore


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", text, flags=re.UNICODE))


def _citation_label(source: dict[str, Any]) -> str:
    authors = source.get("authors") or []
    author = authors[0] if authors else source.get("title", source["id"])
    year = source.get("year") or "n.d."
    return f"{author}, {year}"


def normalize_citations(text: str, sources: list[dict[str, Any]], style: str = "APA") -> str:
    del style  # The formatter is intentionally extensible; APA is the initial normal form.
    source_map = {source["id"]: source for source in sources}

    def replace(match: re.Match[str]) -> str:
        source_id = match.group(1)
        source = source_map.get(source_id)
        return f"({_citation_label(source)})" if source else match.group(0)

    return re.sub(r"\[(S\d+)\]", replace, text)


def _bibliography(sources: list[dict[str, Any]], used_ids: set[str]) -> str:
    if not used_ids:
        return ""
    lines = ["## References", ""]
    for source in sources:
        if source["id"] not in used_ids:
            continue
        location = source.get("url") or source.get("path")
        lines.append(f"- {_citation_label(source)}. {source.get('title', source['id'])}. {location}")
    return "\n".join(lines) + "\n"


def assemble_markdown(
    store: ArtifactStore,
    section_states: list[Any],
    sources: list[dict[str, Any]],
    citation_style: str,
) -> tuple[str, int]:
    parts: list[str] = []
    used_ids: set[str] = set()
    for section in sorted(section_states, key=lambda item: item.order):
        if section.status != "committed":
            raise ValueError(f"cannot assemble uncommitted section: {section.id}")
        if not section.committed_artifact:
            raise ValueError(f"section has no committed artifact: {section.id}")
        draft = store.read_text(section.committed_artifact).strip()
        used_ids.update(re.findall(r"\[(S\d+)\]", draft))
        normalized = normalize_citations(draft, sources, citation_style)
        parts.append(f"## {section.title}\n\n{normalized}")
    content = "\n\n".join(parts).strip() + "\n"
    if used_ids:
        content += "\n" + _bibliography(sources, used_ids)
    count = word_count(content)
    store.write_text("output/final-draft.md", content)
    return content, count


def assemble_latex(
    store: ArtifactStore,
    section_states: list[Any],
    sources: list[dict[str, Any]],
    citation_style: str,
) -> tuple[str, int]:
    del citation_style
    pieces = ["\\documentclass{article}", "\\begin{document}"]
    for section in sorted(section_states, key=lambda item: item.order):
        if section.status != "committed" or not section.committed_artifact:
            raise ValueError(f"cannot assemble uncommitted section: {section.id}")
        text = store.read_text(section.committed_artifact).strip()
        text = re.sub(r"\[(S\d+)\]", r"[\1]", text)
        pieces.extend([f"\\section{{{section.title}}}", text])
    if sources:
        pieces.append("\\section*{References}")
        pieces.extend(f"\\noindent {_citation_label(source)}. {source['title']}.\\\\" for source in sources)
    pieces.append("\\end{document}")
    content = "\n\n".join(pieces) + "\n"
    store.write_text("output/final-draft.tex", content)
    return content, word_count(content)
