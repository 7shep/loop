# Loop

Loop is an assignment-local orchestration engine for schoolwork. It turns an
assignment folder into a review-gated workflow with one visible Codex or
ChatGPT Work conversation and internal planner, researcher, writer, and
reviewer roles.

The implementation is intentionally an orchestration backbone, not one large
prompt: deterministic code owns state, dependencies, retries, artifact writes,
section commits, assembly, and termination; reasoning roles communicate through
small structured files.

## Setup

Loop has no runtime dependencies and supports Python 3.11+.

```bash
python -m pip install -e .
```

The reusable Codex workflow entry point is [skills/loop/SKILL.md](skills/loop/SKILL.md).
Install or copy that skill into the Codex skills directory used by the active
Codex/Work environment. The skill is designed to use the installed `loop`
command through the conversation's tool surface, so the user does not need to
launch a second terminal or switch agent threads.

## Usage

Create an assignment directory with an `assignment.md`, plus optional
`outline.md`, `rubric.md` or `rubric.pdf`, and a `sources/` directory:

```text
Desktop/3rd Year/CISC321/Assignment 1/
├── assignment.md
├── outline.md
├── rubric.md
├── sources/
└── loop.config.json       # optional
```

From the active assignment folder, the Codex workflow is:

```bash
loop run . --runtime conversation
loop tasks . --json
# The active Codex/Work conversation completes the declared task artifact.
loop task-complete . --task-id <task-id>
loop resume . --runtime conversation
```

Repeat the task/complete/resume handoff until Loop reports `completed`. In the
conversation, each task manifest names the role, input artifact references,
output path, model/effort mapping, and allowed scope. The visible conversation
performs the reasoning task; it does not need to create or manage separate user
threads.

Useful controls:

```bash
loop status .
loop pause .
loop resume .
loop cancel .
loop log . --tail 50
loop agents
```

For a complete local smoke path that requires no model access, use the
deterministic demo runtime:

```bash
loop run . --runtime demo
```

Demo prose is synthetic and should not be submitted as coursework. It exists
to validate the full state machine and artifact flow.

## Workflow

The orchestrator creates a global plan and dependency graph, then advances each
runnable section through:

```text
PLAN → PLAN_REVIEW → RESEARCH → WRITE → WRITING_REVIEW → COMMITTED
```

Plan or writing review can send a section back for a bounded revision. Research
records source IDs, evidence IDs, locations, paraphrases, and confidence before
the writer runs. Writers may cite only registered source IDs, represented during
generation as markers such as `[S01]`. The deterministic document builder
normalizes those markers and creates the bibliography.

After assembly, the global reviewer returns `PASS` or structured issues with
affected section IDs. A failed global review reopens only those sections and
reruns their writing/review path. Retry limits move the run to `failed` instead
of allowing an unbounded loop.

## Folder conventions

Loop resolves the path passed to `loop run` into an absolute `workspace_root`.
It reads only beneath that directory and writes generated state only beneath
`.loop/` and `output/`:

```text
Assignment 1/
├── assignment.md                 # immutable user input
├── outline.md                    # optional input
├── rubric.md                     # optional input
├── sources/                      # source files, indexed as S01, S02, ...
├── .loop/
│   ├── state.json                # resumable run state
│   ├── assignment.json           # input references, not a transcript
│   ├── global-plan.json
│   ├── task-graph.json
│   ├── source-index.json
│   ├── evidence.json
│   ├── tasks/                    # queued conversation task manifests
│   ├── agent-results/            # task completion markers
│   ├── sections/01-background/   # plan, reviews, research, draft, commit
│   ├── reviews/global-review.json
│   └── logs/events.jsonl
└── output/
    ├── final-draft.md or final-draft.tex
    └── final.md or final.tex
```

Original assignment and source files are not overwritten by default. Path
containment is checked before every Loop-managed write.

## Configuration

`loop.config.json` is optional and assignment-local. Model names and effort
strings are abstract labels so a future Codex/Work adapter can map them to
available models such as Luna High or Luna xHigh:

```json
{
  "output": "markdown",
  "citation_style": "APA",
  "runtime": "conversation",
  "external_research": false,
  "models": {
    "orchestrator": {"model": "gpt-5.6-luna", "effort": "xhigh"},
    "planner": {"model": "gpt-5.6-luna", "effort": "high"},
    "researcher": {"model": "gpt-5.6-luna", "effort": "high"},
    "writer": {"model": "gpt-5.6-luna", "effort": "xhigh"},
    "reviewer": {"model": "gpt-5.6-luna", "effort": "xhigh"}
  },
  "limits": {
    "max_parallel_sections": 2,
    "max_plan_revisions": 2,
    "max_writing_revisions": 3,
    "max_global_revisions": 2,
    "max_agent_failures": 3
  }
}
```

External research is disabled by default. Enabling it is a deliberate
assignment-level choice for the future provider implementation; the initial
conversation runtime does not silently browse or invent sources.

## Architecture

```text
one visible conversation
        ↓
provider-neutral agent task manifests
        ↓
deterministic orchestrator + dependency graph
        ↓
structured plans / evidence / reviews / drafts in .loop/
        ↓
orchestrator-only section commits
        ↓
deterministic assembly → global review → final output
```

The Python modules are organized by the architecture documents:

```text
src/loop/
├── cli.py                         # one control surface
├── orchestrator.py                # state machine, retries, routing
├── graph.py                       # dependency-aware task graph
├── state.py / models.py           # persisted state and enums
├── workspace.py / artifacts/      # root boundary and atomic storage
├── agents/contracts.py            # role and task contracts
├── agents/conversation.py         # Codex/Work manifest adapter
├── agents/demo.py                 # deterministic smoke runtime
├── schemas.py                     # runtime validation
├── document.py                    # deterministic assembly/citations
└── events.py                      # JSONL event stream
```

JSON Schema versions of the contracts are kept in `schemas/`. The detailed
requirements remain in [PLAN.md](PLAN.md) and
[ARCHITECTURE.md](ARCHITECTURE.md); neither document is replaced by this
implementation.

## First-version boundaries

The local package does not hard-code a Codex SDK, API key, or subscription
endpoint. `ConversationAgentRuntime` queues a least-privilege task manifest and
consumes the artifact completed by the active conversation. This is the
provider seam for real internal Codex thread/session delegation later. Until a
host exposes that delegation API, the roles are isolated by contracts and
artifacts within the one visible conversation rather than pretending that local
code has created hidden threads.

The initial scheduler exposes dependency-aware bounded batches but executes the
batch serially so shared evidence updates remain deterministic. A provider can
replace that runtime with bounded parallel workers without changing the state or
artifact contracts. PDF/DOCX extraction, external search, richer citation
styles, and a live GUI remain follow-on adapters rather than hidden assumptions.

## Verification

Run the foundation tests from the repository root:

```bash
python -m unittest discover -s tests -v
```

The end-to-end test proves that a simple assignment reaches global-review pass,
creates all section artifacts, persists resumable state, and emits the final
Markdown deliverable.
