"""Configuration parsing with safe defaults and an abstract model map."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_MODELS: dict[str, dict[str, str]] = {
    "orchestrator": {"model": "gpt-5.6-luna", "effort": "xhigh"},
    "planner": {"model": "gpt-5.6-luna", "effort": "high"},
    "researcher": {"model": "gpt-5.6-luna", "effort": "high"},
    "writer": {"model": "gpt-5.6-luna", "effort": "xhigh"},
    "reviewer": {"model": "gpt-5.6-luna", "effort": "xhigh"},
    "global_reviewer": {"model": "gpt-5.6-luna", "effort": "xhigh"},
}


@dataclass
class AgentConfig:
    model: str
    effort: str
    timeout_seconds: int = 900

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Limits:
    max_parallel_sections: int = 2
    max_parallel_researchers: int = 3
    max_plan_revisions: int = 2
    max_writing_revisions: int = 3
    max_global_revisions: int = 2
    max_agent_failures: int = 3

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LoopConfig:
    output: str = "markdown"
    citation_style: str = "APA"
    runtime: str = "conversation"
    # When source links are supplied in sources/links.md, native researchers
    # need web access by default to inspect and verify the relevant links.
    external_research: bool = True
    models: dict[str, AgentConfig] = field(default_factory=dict)
    limits: Limits = field(default_factory=Limits)

    def __post_init__(self) -> None:
        if self.output not in {"markdown", "latex"}:
            raise ValueError("output must be 'markdown' or 'latex'")
        if self.runtime not in {"conversation", "demo"}:
            raise ValueError("runtime must be 'conversation' or 'demo'")
        if self.limits.max_parallel_sections < 1 or self.limits.max_parallel_researchers < 1:
            raise ValueError("parallelism limits must be at least 1")
        if any(value < 0 for value in asdict(self.limits).values()):
            raise ValueError("retry and concurrency limits cannot be negative")
        if any(config.timeout_seconds < 1 for config in self.models.values()):
            raise ValueError("agent timeouts must be positive")
        if not self.models:
            self.models = {
                role: AgentConfig(**values) for role, values in DEFAULT_MODELS.items()
            }

    def to_dict(self) -> dict[str, Any]:
        return {
            "output": self.output,
            "citation_style": self.citation_style,
            "runtime": self.runtime,
            "external_research": self.external_research,
            "models": {role: config.to_dict() for role, config in self.models.items()},
            "limits": self.limits.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "LoopConfig":
        """Rehydrate the config snapshot stored with a run."""

        models_raw = raw.get("models", {})
        models = {
            role: AgentConfig(
                model=str(value.get("model", "unmapped")),
                effort=str(value.get("effort", "high")),
                timeout_seconds=int(value.get("timeout_seconds", 900)),
            )
            for role, value in models_raw.items()
            if isinstance(value, dict)
        }
        limit_values = raw.get("limits", {})
        limits = Limits(
            **{
                field_name: int(limit_values.get(field_name, getattr(Limits(), field_name)))
                for field_name in Limits.__dataclass_fields__
            }
        )
        return cls(
            output=str(raw.get("output", "markdown")),
            citation_style=str(raw.get("citation_style", "APA")),
            runtime=str(raw.get("runtime", "conversation")),
            external_research=bool(raw.get("external_research", True)),
            models=models,
            limits=limits,
        )


def _merge_model_config(raw: dict[str, Any]) -> dict[str, AgentConfig]:
    result: dict[str, AgentConfig] = {}
    for role, defaults in DEFAULT_MODELS.items():
        override = raw.get(role, {})
        if not isinstance(override, dict):
            raise ValueError(f"models.{role} must be an object")
        result[role] = AgentConfig(
            model=str(override.get("model", defaults["model"])),
            effort=str(override.get("effort", defaults["effort"])),
            timeout_seconds=int(override.get("timeout_seconds", 900)),
        )
    for role, override in raw.items():
        if role not in result:
            if not isinstance(override, dict):
                raise ValueError(f"models.{role} must be an object")
            result[role] = AgentConfig(
                model=str(override.get("model", "unmapped")),
                effort=str(override.get("effort", "high")),
                timeout_seconds=int(override.get("timeout_seconds", 900)),
            )
    return result


def load_config(root: Path, explicit_path: Path | None = None) -> LoopConfig:
    """Load assignment-local config; never searches outside ``root``."""

    path = explicit_path or root / "loop.config.json"
    if explicit_path is not None and root not in path.resolve().parents and path.resolve() != root:
        raise ValueError("explicit config path must be inside the assignment workspace")
    if not path.exists():
        return LoopConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("loop.config.json must contain an object")
    limits_raw = raw.get("limits", {})
    if not isinstance(limits_raw, dict):
        raise ValueError("limits must be an object")
    limits = Limits(
        **{
            field_name: int(limits_raw.get(field_name, getattr(Limits(), field_name)))
            for field_name in Limits.__dataclass_fields__
        }
    )
    if any(value < 0 for value in asdict(limits).values()):
        raise ValueError("retry and concurrency limits cannot be negative")
    models_raw = raw.get("models", {})
    if not isinstance(models_raw, dict):
        raise ValueError("models must be an object")
    return LoopConfig(
        output=str(raw.get("output", "markdown")).lower(),
        citation_style=str(raw.get("citation_style", "APA")),
        runtime=str(raw.get("runtime", "conversation")).lower(),
        external_research=bool(raw.get("external_research", True)),
        models=_merge_model_config(models_raw),
        limits=limits,
    )
