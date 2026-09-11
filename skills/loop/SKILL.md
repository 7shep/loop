---
name: loop
description: Run a review-gated, evidence-backed school-assignment workflow from the active assignment folder in one Codex or ChatGPT Work conversation.
metadata:
  short-description: Orchestrate an assignment in one conversation
---

# Loop

Loop is the visible-session workflow for turning one assignment directory into a
reviewed Markdown or LaTeX deliverable. The current directory is the assignment
root. Do not inspect parent folders, sibling assignments, or unrelated projects
unless the user explicitly names a path.

## Native subagent execution

This is the primary path. The visible Loop conversation is the orchestrator;
native Codex/Work subagents perform the specialist tasks. When the user invokes
`$loop <request>`, do not do every role in the parent thread and do not ask the
user to switch threads.

1. Capture the request and start the local state machine with
   `loop run . --runtime conversation --request "<request>"`. The command
   initializes `.loop/` and emits the next structured task manifest.
2. Read the pending manifest under `.loop/tasks/`. It names the role, model and
   reasoning effort, artifact inputs, output path, and role contract.
3. Spawn a native subagent for that task using the matching custom agent from
   `agents/` (`loop_planner`, `loop_researcher`, `loop_writer`,
   `loop_reviewer`, or `loop_global_reviewer`) when those definitions have been
   installed into the host's agent directory. Otherwise spawn the host's
   default agent and apply the role contract from the manifest directly. Ask
   the child to read only the listed artifacts, write only the declared output,
   and return a concise summary.
   Native Codex/Work delegation makes the child activity visible in the parent
   conversation and preserves its agent thread for inspection.
   If the host exposes the child thread ID, bind it with
   `loop task-bind . --task-id <task-id> --thread-id <thread-id>` so resume
   state can track the child.
4. After the child completes, validate its JSON/text artifact, run
   `loop task-complete . --task-id <task-id>`, then run
   `loop resume . --runtime conversation` to advance the deterministic runtime.
5. Repeat the delegation loop until Loop reports `completed`, `failed`, or
   `cancelled`. Keep the parent conversation's status updates short; the child
   thread and `.loop/` artifacts hold detailed work.

The parent owns transitions, retries, dependency checks, section commits,
assembly, and global-review routing. Do not skip a gate or manually edit
`.loop/state.json`. The orchestrator is the only component that commits an
approved section into the assembled document.

When native subagent delegation is unavailable in the host, use the same task
manifest flow as a fallback: complete the manifest as a scoped role task in the
visible conversation and mark it complete. This fallback preserves correctness
but does not provide separate child-agent activity.

## Role boundaries

- Orchestrator: interpret requirements and create the global plan and DAG.
- Planner: plan one section; do not draft final prose.
- Reviewer: return structured `APPROVE`/`REVISE` feedback; do not rewrite or
  commit the document.
- Researcher: record traceable evidence and source IDs; do not write prose.
- Writer: use only registered evidence and internal citation markers such as
  `[S01]`; do not introduce a new source.
- Global reviewer: return `PASS` or structured issues with affected section IDs.

If a source is unavailable or the task cannot be completed safely, preserve the
latest artifacts, leave the run paused or failed according to the runtime state,
and explain the concrete blocker in the visible conversation.

For a deterministic smoke test that does not require reasoning-model access,
use `loop run . --runtime demo`. Demo output is synthetic and is not a
replacement for the conversation workflow on real coursework.
