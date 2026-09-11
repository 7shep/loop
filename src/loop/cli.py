"""The single control surface for local and Codex-conversation execution."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agents.conversation import ConversationAgentRuntime
from .agents.contracts import role_definitions
from .artifacts.store import ArtifactStore
from .config import load_config
from .orchestrator import LoopOrchestrator
from .events import EventLog
from .state import load_state, save_state
from .workspace import Workspace, WorkspaceError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loop", description="Run a review-gated assignment workflow.")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="start or continue a run")
    run.add_argument("path", nargs="?", default=".")
    run.add_argument("--runtime", choices=("conversation", "demo"))
    run.add_argument("--config", type=Path)
    run.add_argument("--request", help="the user request to persist with this run")
    run.add_argument("--json", action="store_true", dest="as_json")

    init = commands.add_parser("init", help="create a starter assignment workspace")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--json", action="store_true", dest="as_json")

    resume = commands.add_parser("resume", help="resume an interrupted or paused run")
    resume.add_argument("path", nargs="?", default=".")
    resume.add_argument("--runtime", choices=("conversation", "demo"))
    resume.add_argument("--json", action="store_true", dest="as_json")

    status = commands.add_parser("status", help="show persisted run status")
    status.add_argument("path", nargs="?", default=".")
    status.add_argument("--json", action="store_true", dest="as_json")

    for name in ("pause", "cancel"):
        action = commands.add_parser(name, help=f"{name} the current run")
        action.add_argument("path", nargs="?", default=".")

    agents = commands.add_parser("agents", help="list role contracts")
    agents.add_argument("--json", action="store_true", dest="as_json")

    log = commands.add_parser("log", help="show structured event log")
    log.add_argument("path", nargs="?", default=".")
    log.add_argument("--tail", type=int, default=20)
    log.add_argument("--json", action="store_true", dest="as_json")

    tasks = commands.add_parser("tasks", help="list pending conversation tasks")
    tasks.add_argument("path", nargs="?", default=".")
    tasks.add_argument("--json", action="store_true", dest="as_json")

    complete = commands.add_parser("task-complete", help="mark a queued Codex task complete")
    complete.add_argument("path", nargs="?", default=".")
    complete.add_argument("--task-id", required=True)

    bind = commands.add_parser("task-bind", help="persist a native child-agent thread binding")
    bind.add_argument("path", nargs="?", default=".")
    bind.add_argument("--task-id", required=True)
    bind.add_argument("--thread-id", required=True)
    return parser


def _orchestrator(
    path: str,
    runtime_name: str | None = None,
    config_path: Path | None = None,
    request: str | None = None,
) -> LoopOrchestrator:
    workspace = Workspace.discover(path)
    config = load_config(workspace.root, config_path)
    if runtime_name:
        config.runtime = runtime_name
    return LoopOrchestrator(workspace, config=config, reporter=print, request=request)


def _print_result(result: object, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(result.__dict__, indent=2))
    else:
        print(getattr(result, "message", result))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            result = Workspace.discover(args.path).initialize()
            _print_result(result, args.as_json)
            return 0
        if args.command == "agents":
            value = {name: role.to_dict() for name, role in role_definitions().items()}
            print(json.dumps(value, indent=2, ensure_ascii=False) if args.as_json else "\n".join(value))
            return 0
        if args.command in {"run", "resume"}:
            orchestrator = _orchestrator(
                args.path,
                args.runtime,
                getattr(args, "config", None),
                getattr(args, "request", None),
            )
            result = orchestrator.run(resume=args.command == "resume")
            _print_result(result, args.as_json)
            return 0 if result.status not in {"failed", "cancelled"} else 1
        if args.command == "status":
            snapshot = _orchestrator(args.path).status_snapshot()
            print(json.dumps(snapshot, indent=2) if args.as_json else _status_text(snapshot))
            return 0
        if args.command in {"pause", "cancel"}:
            orchestrator = _orchestrator(args.path)
            result = orchestrator.pause() if args.command == "pause" else orchestrator.cancel()
            _print_result(result)
            return 0
        if args.command == "log":
            workspace = Workspace.discover(args.path)
            events_path = workspace.inside(".loop/logs/events.jsonl")
            lines = events_path.read_text(encoding="utf-8").splitlines()[-args.tail :] if events_path.exists() else []
            value = [json.loads(line) for line in lines if line.strip()]
            print(json.dumps(value, indent=2) if args.as_json else "\n".join(
                f"{item['timestamp']} {item['type']}" for item in value
            ))
            return 0
        if args.command == "tasks":
            workspace = Workspace.discover(args.path)
            store = ArtifactStore(workspace)
            task_dir = workspace.inside(".loop/tasks")
            value = []
            for path in sorted(task_dir.glob("*.json")):
                task = store.read_json(workspace.relative(path))
                result_ref = f".loop/agent-results/{task['task_id']}.json"
                if not store.exists(result_ref):
                    value.append(task)
            print(json.dumps(value, indent=2) if args.as_json else "\n".join(
                f"{task['task_id']} [{task['role']}] -> {task['output_ref']}" for task in value
            ))
            return 0
        if args.command == "task-complete":
            workspace = Workspace.discover(args.path)
            store = ArtifactStore(workspace)
            result_ref = ConversationAgentRuntime.complete_task(args.task_id, store)
            print(f"completed {args.task_id} ({result_ref})")
            return 0
        if args.command == "task-bind":
            workspace = Workspace.discover(args.path)
            store = ArtifactStore(workspace)
            state = load_state(store)
            manifest_ref = f".loop/tasks/{args.task_id}.json"
            if not store.exists(manifest_ref):
                raise ValueError(f"unknown task: {args.task_id}")
            manifest = store.read_json(manifest_ref)
            manifest["thread_id"] = args.thread_id
            store.write_json(manifest_ref, manifest)
            state.agent_threads[args.task_id] = {
                "thread_id": args.thread_id,
                "role": manifest.get("role"),
                "section_id": manifest.get("metadata", {}).get("section", {}).get("id"),
                "status": "running",
            }
            save_state(store, state)
            EventLog(store, state.run_id).emit(
                "AGENT_THREAD_BOUND",
                task_id=args.task_id,
                thread_id=args.thread_id,
                role=manifest.get("role"),
            )
            print(f"bound {args.task_id} to {args.thread_id}")
            return 0
    except (WorkspaceError, ValueError, RuntimeError, OSError) as exc:
        print(f"loop: {exc}", file=sys.stderr)
        return 2
    return 2


def _status_text(snapshot: dict[str, object]) -> str:
    sections = snapshot.get("sections", {})
    lines = [
        f"Loop {snapshot['run_id']} — {snapshot['status']}",
        f"Phase: {snapshot['phase']}",
        f"Workspace: {snapshot['workspace_root']}",
        f"Sections: {sections}",
    ]
    if snapshot.get("waiting_for_task"):
        lines.append(f"Waiting for task: {snapshot['waiting_for_task']}")
    if snapshot.get("last_error"):
        lines.append(f"Error: {snapshot['last_error']}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
