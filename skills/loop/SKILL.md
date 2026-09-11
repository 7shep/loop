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

## Conversation execution

Use the installed `loop` command through the available Codex tool surface; the
user should not need to open another terminal or switch agent threads.

1. Start or continue the run with `loop run . --runtime conversation`.
2. If the run pauses, inspect `loop tasks . --json` and read the pending task
   manifest under `.loop/tasks/`. It contains the role, model/effort mapping,
   input artifact references, output path, and contract.
3. Perform exactly that role as a scoped internal task. Read the referenced
   artifacts rather than passing large transcripts. Write only the declared
   output artifact under `.loop/` or the section draft path. Reviewers write
   review artifacts and never mutate committed output.
4. Validate structured JSON against the contract in the manifest. Mark the task
   complete with `loop task-complete . --task-id <task-id>`.
5. Resume with `loop resume . --runtime conversation` and repeat until Loop
   reports `completed`, `failed`, or `cancelled`.

The runtime owns transitions, retries, dependency checks, section commits,
assembly, and global-review routing. Do not skip a gate or manually edit
`.loop/state.json` to force progress. The orchestrator is the only component
that commits an approved section into the assembled document.

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
