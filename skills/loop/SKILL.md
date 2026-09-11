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

## Assignment guidance inputs

`assignment.md` and `sources/links.md` are required. Assignment guidance belongs
in an optional `outline/` directory; it is a collection, not a single required
filename. Every file below that directory is indexed and passed to the relevant
agents, including PDFs, Markdown, text, and nested files. The sources directory
has a fixed entry point and an optional historical-feedback collection:

```text
sources/
├── links.md                   # required HTTP(S) source links
├── past-grade.pdf             # optional
├── professor-feedback.docx    # optional
└── previous-comments.txt      # optional
```

Optional source feedback files must be PDF, DOCX, or text files. They are
historical guidance and are never citation sources. Each HTTP(S) link in
`sources/links.md` becomes a registered web source (`S01`, `S02`, ...):

```text
outline/
├── assignment-outline.pdf     # or .md/.txt
├── rubric.pdf                 # optional
├── past-marks.pdf             # optional legacy location
└── professor-feedback.md      # optional legacy location
```

Loop classifies likely rubric and past-mark/feedback files in
`.loop/outline-index.json`, while still passing every `outline/` artifact to the
agents so an unusual filename is not silently ignored. It passes `links.md` and
the optional source-feedback files to every relevant task, and gives the
researcher web-search instructions for opening and evaluating the listed links.
Root-level
`outline.md`/`rubric.*` inputs remain a compatibility path for older assignment
folders.

When past marks or professor feedback are present, every planning, research,
writing, and review task must read them and extract supported recurring reasons
marks were lost. Convert those reasons into concrete do/not-do checks and apply
them alongside the current assignment outline and rubric. Historical feedback is
guidance, not a replacement for current requirements: never invent prior issues,
copy old assignment content, cite feedback files, or let an old rubric override
the current one.

## Native subagent execution

This is the primary path. The visible Loop conversation is the orchestrator;
native Codex/Work subagents perform the specialist tasks. When the user invokes
`$loop <request>`, do not do every role in the parent thread and do not ask the
user to switch threads.

1. Capture the request and start the local state machine with
   `loop run . --runtime conversation --request "<request>"`. The command
   initializes `.loop/` and emits the next structured task manifest.
2. Read the pending manifest under `.loop/tasks/`. It names the role, model and
   reasoning effort, artifact inputs (including `.loop/outline-index.json`,
   `outline/` files, `sources/links.md`, and optional source feedback files),
   output path, and role contract.
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

All roles must use the indexed outline artifacts as assignment constraints. When
past-mark or professor-feedback artifacts exist, they must carry the extracted
do/not-do checks into their own output or review criteria without treating those
historical records as current requirements.

If a source is unavailable or the task cannot be completed safely, preserve the
latest artifacts, leave the run paused or failed according to the runtime state,
and explain the concrete blocker in the visible conversation.

For a deterministic smoke test that does not require reasoning-model access,
use `loop run . --runtime demo`. Demo output is synthetic and is not a
replacement for the conversation workflow on real coursework.
