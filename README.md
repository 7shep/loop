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
Codex/Work environment. Its primary path asks the native Codex/Work runtime to
spawn role-specific subagents, so the user sees their activity in the parent
conversation without switching threads. The packaged TOML definitions in
`skills/loop/agents/` can be copied to `~/.codex/agents/` or to the assignment's
`.codex/agents/` for named role defaults. Install or copy the companion
[humanizer skill](skills/humanizer/SKILL.md) under the `humanizer` name as well;
it is a required final writer pass.

## Usage

Initialize a new assignment workspace from the class or course directory:

```bash
loop init CISC335
```

This creates a `CISC335/` child directory with the canonical `assignment.md`,
`outline/`, `sources/links.md`, `.loop/`, and `output/` layout, along with a
starter `README.md` that explains the workflow. Existing files are preserved,
so initializing the same assignment again is safe.

Create an assignment directory with an `assignment.md`, an optional `outline/`
directory, and an optional `sources/` directory. If the assignment uses outside
sources, put their links in `sources/links.md`. Optional source-folder files are
historical grades or professor feedback in PDF, DOCX, or text format:

```text
Desktop/3rd Year/CISC321/Assignment 1/
├── assignment.md
├── outline/
│   ├── assignment-outline.pdf  # .md/.txt also work; filename is not fixed
│   └── rubric.pdf               # optional
├── sources/
│   ├── links.md                 # optional HTTP(S) links to outside sources
│   ├── past-grade.pdf           # optional historical feedback
│   ├── professor-feedback.docx  # optional historical feedback
│   └── previous-comments.txt    # optional historical feedback
└── loop.config.json       # optional
```

Loop indexes every file under `outline/`, including nested files and PDFs. When
`sources/links.md` is present, Loop extracts each HTTP(S) link into
`.loop/source-index.json` as a citable web source. An empty or missing links file
is valid for assignments that do not use outside sources. Optional files beside `links.md` are passed to agents as
historical feedback only; they are never registered as citation sources. Agents
extract supported reasons marks were lost and turn them into concrete do/not-do
checks, while keeping the current assignment requirements and rubric
authoritative. They must not invent historical issues or copy old work.
Root-level `outline.md` and `rubric.*` remain supported for compatibility with
older folders.

From the active assignment folder, invoke the skill in the parent conversation:

```text
> $loop Complete the assignment in this folder using the supplied sources.
```

The parent Loop conversation creates the state machine, then delegates planner,
researcher, writer, and reviewer work to native subagents. Their activity and
results remain visible in the Codex CLI/Work parent session. Each writer drafts
from the approved evidence and then invokes `$humanizer` in embedded mode before
writing its section draft. The skill edits prose only, preserving supported
claims, headings, format, and `[S##]` citation markers.

The deterministic control commands used by the parent workflow are:

```bash
loop run . --runtime conversation --request "Complete the assignment in this folder using the supplied sources."
loop tasks . --json
# The parent conversation delegates the pending task to a native subagent.
loop task-complete . --task-id <task-id>
loop task-bind . --task-id <task-id> --thread-id <native-thread-id>
loop resume . --runtime conversation
```

The parent repeats the handoff until Loop reports `completed`. Each task
manifest names the role, model/effort mapping, artifact inputs, output path, and
contract, including any `required_skills`. If native delegation is unavailable,
the parent may complete the manifest itself as a fallback and must invoke
`$humanizer` for writer tasks; that preserves correctness but does not show
separate child-agent activity.

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
generation as markers such as `[S01]`. After drafting, the writer invokes the
required humanizer pass and verifies that the same citation markers and claims
survive. The deterministic document builder normalizes those markers and creates
the bibliography.

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
├── outline/                      # optional outline and rubric inputs
│   ├── assignment-outline.pdf    # PDF, Markdown, text, and nested files work
│   ├── rubric.pdf                # optional
├── sources/                      # optional links + optional grade feedback
│   ├── links.md                 # optional outside-source links
│   ├── past-grade.pdf           # optional; not citable
│   └── professor-feedback.docx  # optional; not citable
├── .loop/
│   ├── state.json                # resumable run state
│   ├── assignment.json           # input references, not a transcript
│   ├── outline-index.json        # categorized outline/history references
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

Original assignment, links, and feedback files are not overwritten by default. Path
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
  "external_research": true,
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

External research is enabled by default so the researcher can use web search to
open and evaluate the links in `sources/links.md`. Set `external_research` to
`false` when an assignment must not use network access; this does not add any
new sources to the allowlist.

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
├── runtime/                        # provider/runtime export seam
├── schemas.py                     # runtime validation
├── document.py                    # deterministic assembly/citations
└── events.py                      # JSONL event stream
```

JSON Schema versions of the contracts are kept in `schemas/`. The detailed
requirements remain in [PLAN.md](PLAN.md) and
[ARCHITECTURE.md](ARCHITECTURE.md); neither document is replaced by this
implementation.

## First-version boundaries

Native Codex/Work delegation is the intended execution surface. The parent
skill delegates each manifest to a native child agent and then uses the local
orchestrator to validate the artifact and advance state. This provides visible
child-agent activity in the same parent conversation. The local package does
not call a private API or require a separate API key; it uses the host's
authenticated subagent capability.

Codex CLI and ChatGPT Work must have native subagents enabled for that activity
to appear. The packaged role definitions follow the host's custom-agent format;
copy them to the host's global agent directory or the active assignment's
project-scoped `.codex/agents/` during setup.

`ConversationAgentRuntime` remains the portable fallback for hosts that expose
file tools but not native subagent delegation. It queues a least-privilege task
manifest for the parent session to complete, but cannot create child threads or
stream their activity itself.

The initial scheduler exposes dependency-aware bounded batches but executes the
batch serially so shared evidence updates remain deterministic. A provider can
replace that runtime with bounded parallel workers without changing the state or
artifact contracts. PDF/DOCX inputs are accepted and passed to native agents by
reference; provider-specific PDF/DOCX text extraction for the deterministic
local runtime, richer citation styles, and a live GUI remain follow-on adapters
rather than hidden assumptions. Native researcher subagents use their web
search access to inspect the links from `sources/links.md`. The humanizer skill
does not add a network or source lookup step.

## Verification

Run the foundation tests from the repository root:

```bash
python -m unittest discover -s tests -v
```

The end-to-end test proves that a simple assignment reaches global-review pass,
creates all section artifacts, persists resumable state, and emits the final
Markdown deliverable.
