# Loop — Architecture

## 1. Architectural Summary

Loop uses a **supervisor/orchestrator architecture** in which the user interacts with one top-level session while multiple isolated Codex agent sessions perform specialized work underneath it. Each run is rooted in a user-selected assignment directory, which becomes the security, persistence, and artifact boundary for that run.

The architecture deliberately separates:

- workflow control
- planning
- research
- writing
- review
- persistence
- document assembly

The central design rule is:

> Deterministic code controls the workflow. Agents perform tasks that require judgment or reasoning.

---

## 2. High-Level Architecture

```text
                           USER
                            │
                 $ loop run <assignment-dir>
                            │
                            ▼
                 ┌────────────────────┐
                 │    ORCHESTRATOR    │
                 │ GPT-5.6 Luna xHigh │
                 └─────────┬──────────┘
                           │
                           ▼
                    GLOBAL TASK GRAPH
                           │
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
          SECTION A     SECTION B     SECTION C
             │             │             │
             ▼             ▼             ▼
          Planner        Planner        Planner
             │             │             │
             ▼             ▼             ▼
          Reviewer       Reviewer       Reviewer
             │             │             │
             ▼             ▼             ▼
         Researcher     Researcher     Researcher
             │             │             │
             ▼             ▼             ▼
           Writer          Writer          Writer
             │             │             │
             ▼             ▼             ▼
      Humanizer (writer) Humanizer (writer) Humanizer (writer)
             │             │             │
             ▼             ▼             ▼
          Reviewer       Reviewer       Reviewer
             │             │             │
             └─────────────┼─────────────┘
                           ▼
                    APPROVED SECTIONS
                           │
                           ▼
                  DETERMINISTIC BUILDER
                           │
                           ▼
                    final-draft.md
                           │
                           ▼
                 ┌───────────────────┐
                 │  GLOBAL REVIEWER  │
                 │ Luna xHigh        │
                 └─────────┬─────────┘
                           │
                     PASS / REVISE
                           │
                           ▼
                       final.md
```

---

## 3. Runtime Layers

Loop should be divided into four main layers.

Reusable skills are execution policy applied inside an agent task. They do not
become independent state-machine nodes or persisted artifacts unless a workflow
explicitly requires one. The writer's required `humanizer` skill is therefore a
substep between drafting and writing-review, inside the writer invocation.

```text
┌───────────────────────────────────────────────┐
│               INTERFACE LAYER                 │
│ CLI / future ChatGPT integration              │
├───────────────────────────────────────────────┤
│             ORCHESTRATION LAYER               │
│ state machine / DAG scheduler / retries       │
├───────────────────────────────────────────────┤
│                 AGENT LAYER                   │
│ planner / researcher / writer / reviewer      │
├───────────────────────────────────────────────┤
│              ARTIFACT LAYER                   │
│ files / state / evidence / outputs / logs     │
└───────────────────────────────────────────────┘
```

---

## 4. Interface Layer

The interface layer provides a single control surface.

Initial implementation:

```bash
cd "Desktop/3rd Year/CISC321/Assignment 1"
loop run .
```

The current assignment directory is the workspace root. Parent folders such as `3rd Year/` and `CISC321/` are organizational context only and are not automatically traversed.

Future interactive mode:

```text
$ loop

> Run the assignment in this directory.

[Loop] Parsing assignment...
[Loop] 6 sections identified.
[Loop] Starting research for Sections 2 and 3.

> status

[Loop] 43% complete...
```

The interface should never require the user to manually enter individual agent sessions.

---


## 5. Workspace Root and Filesystem Boundary

Every Loop run is anchored to exactly one assignment directory.

Example:

```text
Desktop/
└── 3rd Year/
    └── CISC321/
        └── Assignment 1/          ← workspace_root
            ├── assignment.md
            ├── outline/
            │   ├── assignment-outline.pdf
            │   ├── rubric.pdf
            │   └── notes.md
            ├── sources/
            │   ├── links.md
            │   └── past-grade.pdf
            ├── .loop/
            └── output/
```

The runtime resolves the path supplied to `loop run` and stores it as `workspace_root`.

`assignment.md` is the required assignment prompt. Assignment guidance is an
optional `outline/` directory containing any number of outline, rubric, PDF, or
past-mark/professor-feedback files; no filename such as `rubric.pdf` is required.
Loop indexes every file in that directory in `.loop/outline-index.json` and
passes the references to the relevant roles. Historical feedback is converted
by reasoning agents into supported do/not-do checks, while the current outline
and rubric remain authoritative. Root-level `outline.md` and `rubric.*` remain
supported as a compatibility path. `sources/links.md` is required. Its HTTP(S)
links become the only registered citation sources, while optional PDF, DOCX, and
text files in `sources/` are passed as historical grade-feedback guidance and
are never citable.

```ts
interface Workspace {
  root: AbsolutePath;
  loopDir: AbsolutePath;
  outputDir: AbsolutePath;
}
```

Default path rules:

1. Agents may read files recursively beneath `workspace_root`.
2. Agents may write only to approved generated paths such as `.loop/` and `output/`, unless the user explicitly permits another destination.
3. Parent directories and sibling assignment/course folders are outside the default sandbox.
4. Relative file references are resolved against `workspace_root`.
5. Original user files are treated as immutable inputs by default.
6. Every spawned Codex session receives the same assignment root as its working directory.

This guarantees that running Loop in:

```text
Desktop/3rd Year/CISC321/Assignment 1/
```

cannot accidentally pull context from:

```text
Desktop/3rd Year/CISC321/Assignment 2/
Desktop/3rd Year/MATH221/
```

unless explicitly requested.

### Local Runtime Layout

```text
Assignment 1/
├── assignment.md
├── outline/
│   ├── assignment-outline.pdf
│   ├── rubric.pdf
│   └── notes.md
├── sources/
│   ├── links.md
│   └── past-grade.pdf
│
├── .loop/
│   ├── state.json
│   ├── outline-index.json
│   ├── global-plan.json
│   ├── source-index.json
│   ├── evidence.json
│   ├── sections/
│   │   ├── 01-background/
│   │   │   ├── plan.json
│   │   │   ├── plan-review.json
│   │   │   ├── research.json
│   │   │   ├── draft.md
│   │   │   └── writing-review.json
│   │   └── ...
│   ├── reviews/
│   └── logs/
│
└── output/
    ├── final-draft.md
    └── final.md
```

`.loop/` contains machine state and intermediate artifacts. `output/` contains user-facing deliverables.

---

## 6. Orchestration Layer

The orchestration layer is the core of the product.

It should contain normal application code responsible for:

- project initialization
- run IDs
- persistent state
- state transitions
- dependency management
- scheduling
- bounded parallelism
- retries
- timeouts
- agent invocation
- schema validation
- artifact routing
- section commit
- global assembly
- termination

The orchestration layer should not delegate simple control-flow decisions to an LLM.

For example:

```ts
if (section.plan.status === "approved") {
  scheduleResearch(section.id);
}
```

is preferred over asking an agent whether research should start.

---

## 7. Orchestrator Agent

The orchestrator agent is distinct from the orchestration runtime.

### Orchestration Runtime

Deterministic software.

### Orchestrator Agent

Reasoning component used when interpretation is required.

Recommended model:

```text
GPT-5.6 Luna xHigh
```

Responsibilities:

- interpret the assignment
- identify logical sections
- determine section dependencies
- recommend execution order
- identify project-wide constraints
- decide how global reviewer feedback maps to affected sections

It should output structured data rather than directly manipulating process state.

Example:

```json
{
  "sections": [
    {
      "id": "background",
      "title": "Historical Background",
      "depends_on": []
    },
    {
      "id": "argument",
      "title": "Main Argument",
      "depends_on": ["background"]
    }
  ]
}
```

The runtime validates this output and updates state.

---

## 8. Global Task Graph

Assignments are represented as a directed acyclic graph where possible.

Example:

```text
             Background
                 │
          ┌──────┴──────┐
          ▼             ▼
      Argument     Counterargument
          └──────┬──────┘
                 ▼
              Analysis
                 │
                 ▼
             Conclusion
                 │
                 ▼
            Introduction
```

This allows:

- parallel execution
- explicit dependencies
- selective reruns
- efficient failure recovery

Suggested representation:

```json
{
  "nodes": [
    {
      "id": "analysis",
      "depends_on": ["argument", "counterargument"],
      "status": "pending"
    }
  ]
}
```

---

## 8. Section State Machine

Every section is represented by a deterministic state machine.

```text
PENDING
   ↓
PLANNING
   ↓
PLAN_REVIEW
   ├── rejected ──→ PLANNING
   ↓ approved
RESEARCHING
   ↓
WRITING
   │ writer drafts, then invokes humanizer
   ↓
WRITING_REVIEW
   ├── rejected ──→ WRITING
   ↓ approved
APPROVED
   ↓
COMMITTED
```

Failure states should be explicit:

```text
FAILED
PAUSED
CANCELLED
```

---

## 9. Agent Isolation

Each specialized agent should run in its own Codex thread/session.

Example:

```text
Top-Level Loop Session
│
├── Orchestrator Thread
├── Section-01 Planner Thread
├── Section-01 Reviewer Thread
├── Section-01 Research Thread
├── Section-01 Writer Thread (invokes humanizer)
├── Section-02 Planner Thread
└── ...
```

The user does not manually switch between these threads.

Agent thread identifiers are internal implementation details stored in project state.

---

## 10. Shared Memory Model

Agents should communicate primarily through persisted artifacts rather than enormous transcripts.

Bad architecture:

```text
Researcher outputs 30,000 tokens
        ↓
Writer receives 30,000 tokens
        ↓
Reviewer receives entire conversation
```

Preferred architecture:

```text
Researcher
   ↓
research.json / evidence.json
   ↓
Writer reads only required evidence
   ↓
draft.md
   ↓
Reviewer reads draft + relevant evidence
```

The filesystem acts as shared memory.

---

## 11. Agent Contracts

Every agent invocation should have:

```text
ROLE
INPUT SCHEMA
OUTPUT SCHEMA
REQUIRED SKILLS
ALLOWED TOOLS
WORKING DIRECTORY
MODEL
REASONING EFFORT
TIMEOUT
```

Role definitions declare any required skills, and the runtime copies that list
onto every task manifest. The writer therefore carries
`required_skills: ["humanizer"]` in both its role contract and its concrete task
handoff, where the parent or native child can enforce the required invocation.

Agents should not return arbitrary free-form responses when the runtime needs structured decisions.

---

## 12. Planner Contract

### Input

```json
{
  "assignment": {},
  "global_constraints": {},
  "section": {},
  "related_sections": [],
  "available_sources": [],
  "outline_guidance": {
    "files": [],
    "past_marks_files": [],
    "must_do": [],
    "must_not_do": []
  }
}
```

### Output

```json
{
  "section_id": "argument",
  "objective": "Establish X",
  "target_words": 650,
  "claims": [
    {
      "id": "C1",
      "statement": "...",
      "evidence_required": ["scholarly source"]
    }
  ],
  "structure": [
    "opening claim",
    "evidence",
    "analysis"
  ]
}
```

Recommended model:

```text
GPT-5.6 Luna High
```

---

## 13. Researcher Contract

### Input

- approved section plan
- source registry
- `sources/links.md` and its allowlisted HTTP(S) links
- optional PDF, DOCX, and text grade-feedback files under `sources/`
- outline guidance and any past-mark/professor-feedback artifacts
- web-search permission

### Output

```json
{
  "section_id": "argument",
  "claims": [
    {
      "claim_id": "C1",
      "evidence": ["S02-E03", "S05-E01"]
    }
  ]
}
```

The researcher may append verified evidence records to the shared evidence store.

Recommended model:

```text
GPT-5.6 Luna High
```

Escalate to xHigh only for unusually difficult source interpretation.

---

## 14. Writer Contract

### Input

- approved section plan
- verified evidence subset
- citation rules
- style requirements
- outline guidance and any applicable past-mark do/not-do checks
- relevant approved prior sections where necessary
- required `humanizer` skill

### Output

```text
draft.md
```

The writer first drafts from the approved plan and evidence, then invokes
`humanizer` in embedded mode on the complete draft before writing `draft.md`.
The skill may change prose structure and wording to remove AI-sounding patterns,
but it must preserve every supported claim, required heading and format, and
the full set of registered `[S##]` citation markers. The writer verifies those
invariants after the pass and returns only the final humanized text.

The humanizer does not research, add sources, or replace the writing reviewer.
If the required skill is unavailable, the writer pauses or reports a concrete
blocker rather than silently producing an unprocessed draft. The writer should
not independently invent sources.

Recommended model:

```text
GPT-5.6 Luna xHigh
```

---

## 15. Reviewer Contract

The reviewer has two modes.

### Plan Review

Input:

- section plan
- assignment requirements
- global plan
- outline guidance, including applicable past-mark do/not-do checks

Output:

```json
{
  "decision": "APPROVE",
  "issues": []
}
```

### Writing Review

Input:

- draft
- approved plan
- cited evidence
- assignment constraints
- outline guidance, including applicable past-mark do/not-do checks

Output:

```json
{
  "decision": "REVISE",
  "score": 86,
  "critical_issues": [],
  "citation_issues": [],
  "argument_issues": [],
  "formatting_issues": []
}
```

Recommended model:

```text
GPT-5.6 Luna xHigh
```

The reviewer must never commit directly to the final document.

---

## 16. Source Registry

All sources should have canonical internal IDs.

```json
{
  "id": "S01",
  "title": "Example Source",
  "authors": [],
  "year": null,
  "type": "web",
  "path": "sources/links.md",
  "url": "https://example.com/source",
  "verified": true
}
```

The source registry is the authoritative list of allowed citations. It is
derived from the HTTP(S) links in the required `sources/links.md`; optional
grade-feedback files are not registered sources.

---

## 17. Evidence Registry

Evidence is stored separately from source metadata.

```json
{
  "id": "S03-E04",
  "source_id": "S03",
  "supports": ["section-02:C1"],
  "location": "p. 17",
  "paraphrase": "...",
  "confidence": "high"
}
```

This creates traceability:

```text
Paragraph
  ↓
Claim
  ↓
Evidence ID
  ↓
Source ID
  ↓
Original source
```

---

## 18. Citation Firewall

The writer should reference only registered sources/evidence.

A useful internal rule is:

```text
WRITER MAY NOT INTRODUCE A NEW SOURCE.
WRITER MAY ONLY CITE SOURCE IDs PRESENT IN THE REGISTRY.
HUMANIZER MUST PRESERVE THE WRITER'S REGISTERED CITATION MARKERS.
```

The output may temporarily use internal markers:

```text
The effect became more pronounced over time [S03].
```

A deterministic citation formatter converts these markers into the requested citation style.

Example:

```text
[S03]
```

becomes:

```text
(Smith, 2024)
```

---

## 19. Document Builder

The final document builder should be normal code, not an agent.

Responsibilities:

- select approved section version
- order sections
- concatenate content
- apply headings
- normalize citation markers
- generate bibliography
- validate word counts
- generate Markdown or LaTeX

Example:

```ts
for (const section of orderedSections) {
  assert(section.status === "approved");
  document.append(section.finalDraft);
}
```

---

## 20. Global Review

After assembly, the global reviewer evaluates the complete document.

Input:

```text
final-draft.md
assignment requirements
global plan
source registry
```

Output:

```json
{
  "decision": "REVISE",
  "issues": [
    {
      "type": "CONTRADICTION",
      "sections": ["section-02", "section-04"],
      "description": "..."
    }
  ]
}
```

The orchestrator maps issues back to section pipelines.

---

## 21. Selective Revision

Global failures should not restart the entire assignment.

Example:

```text
Global reviewer finds problem in Sections 2 and 4
                  │
          ┌───────┴───────┐
          ▼               ▼
      reopen S2        reopen S4
          │               │
          ▼               ▼
        Writer           Writer
          │               │
          ▼               ▼
       Reviewer         Reviewer
          └───────┬───────┘
                  ▼
               rebuild
                  ▼
             global review
```

---

## 22. Persistent State

Suggested `.loop/state.json`:

```json
{
  "run_id": "run_20260911_001",
  "status": "running",
  "current_phase": "section_execution",
  "sections": {
    "background": {
      "status": "committed",
      "plan_revision": 1,
      "draft_revision": 2
    },
    "argument": {
      "status": "writing_review",
      "plan_revision": 1,
      "draft_revision": 1
    }
  },
  "global_review_cycle": 0
}
```

State writes should be atomic where possible.

---

## 23. Event System

Agent and runtime activity should emit structured events.

Examples:

```text
RUN_STARTED
SECTION_STARTED
PLAN_CREATED
PLAN_REJECTED
PLAN_APPROVED
RESEARCH_STARTED
RESEARCH_COMPLETED
DRAFT_CREATED
DRAFT_REJECTED
SECTION_APPROVED
SECTION_COMMITTED
GLOBAL_REVIEW_STARTED
GLOBAL_REVIEW_FAILED
RUN_COMPLETED
```

Events power:

- CLI updates
- logs
- future GUI
- debugging
- progress tracking

---

## 24. Concurrency Model

Concurrency should be dependency-aware and bounded.

Pseudo-code:

```ts
while (!graph.complete()) {
  const runnable = graph
    .readyNodes()
    .slice(0, config.maxParallelSections);

  await Promise.all(runnable.map(runSection));
}
```

The system should never spawn unlimited Codex workers.

---

## 25. Retry Policy

Retries should be explicit and bounded.

Example:

```text
planner review rejection: max 2 revisions
writer review rejection: max 3 revisions
agent execution failure: max 3 retries
global review: max 2 full cycles
```

After exhausting a limit, the run moves to a failed or needs-user state rather than looping forever.

---

## 26. Model Allocation

Baseline recommendation:

| Role | Model | Effort |
|---|---|---|
| Orchestrator | GPT-5.6 Luna | xHigh |
| Section Planner | GPT-5.6 Luna | High |
| Researcher | GPT-5.6 Luna | High |
| Writer | GPT-5.6 Luna | xHigh |
| Reviewer | GPT-5.6 Luna | xHigh |
| Global Reviewer | GPT-5.6 Luna | xHigh |

Mechanical tasks such as citation formatting, file concatenation, status tracking, and schema validation should not use model calls.

---

## 27. Codex Runtime Integration

Loop should expose a provider abstraction rather than tightly coupling orchestration logic to one invocation mechanism.

Example:

```ts
interface AgentRuntime {
  createThread(options: ThreadOptions): Promise<ThreadId>;
  run(threadId: ThreadId, task: AgentTask): Promise<AgentResult>;
  resume(threadId: ThreadId, task: AgentTask): Promise<AgentResult>;
  cancel(threadId: ThreadId): Promise<void>;
}
```

Initial implementation:

```text
Codex Runtime Adapter
```

Authentication should use the user's existing Codex/ChatGPT login where supported rather than requiring an API key.

This abstraction leaves room for other runtimes later without rewriting the orchestration engine.

---

## 28. Tool Permissions

Agents should receive only the tools they need.

Example:

### Planner

```text
read project artifacts
no shell mutation
no final document writes
```

### Researcher

```text
read sources/links.md and optional grade-feedback files
use web search to inspect relevant links when enabled
write research/evidence artifacts
```

### Writer

```text
read approved plan
read evidence
invoke humanizer in embedded mode after drafting
write only the final humanized section draft path
preserve supported claims and [S##] markers
```

### Reviewer

```text
read-only access to draft/evidence/requirements
write only review artifact
```

Least-privilege agent tooling reduces accidental mutations.

---

## 29. Context Management

Each agent invocation should receive only relevant context.

Do not pass the entire project transcript.

Example writer context:

```text
assignment constraints
+ approved section plan
+ evidence for this section
+ relevant neighboring approved sections
+ citation/style rules
+ humanizer skill instructions
```

This reduces token usage and context drift.

---

## 30. Manual Intervention

The orchestration runtime should support user commands while a run is active.

Examples:

```text
pause
resume
cancel
status
remove-source S07
change-output latex
```

For requirement changes, the runtime should invalidate affected artifacts rather than restarting blindly.

Example:

```text
User removes Source S07
        ↓
Find claims backed by S07
        ↓
Invalidate affected drafts
        ↓
Schedule replacement research
```

---

## 31. Failure Recovery

Loop should recover from:

- process crash
- Codex thread failure
- malformed JSON
- timeout
- invalid plan graph
- unavailable source
- research failure
- review loop exhaustion

Because each stage writes persistent artifacts, recovery should resume from the latest valid state rather than rerun completed stages.

---

## 32. Security and Isolation

The runtime should treat user source files and agent-generated commands carefully.

Recommended controls:

- project-root sandbox
- explicit network permission
- no writes outside workspace
- allowlisted commands where practical
- configurable approval modes
- audit logs
- maximum runtime
- maximum child processes

Research agents may need broader network access than writers/reviewers.

---

## 33. Suggested Module Structure

```text
src/
├── cli/
│   ├── commands.ts
│   └── renderer.ts
│
├── core/
│   ├── orchestrator.ts
│   ├── state-machine.ts
│   ├── scheduler.ts
│   ├── task-graph.ts
│   └── events.ts
│
├── agents/
│   ├── planner.ts
│   ├── researcher.ts
│   ├── writer.ts
│   ├── reviewer.ts
│   └── global-reviewer.ts
│
├── skills/
│   ├── loop/SKILL.md
│   └── humanizer/SKILL.md
│
├── runtime/
│   ├── agent-runtime.ts
│   └── codex-runtime.ts
│
├── artifacts/
│   ├── store.ts
│   ├── sources.ts
│   ├── evidence.ts
│   └── documents.ts
│
├── schemas/
│   ├── plan.ts
│   ├── review.ts
│   ├── evidence.ts
│   └── state.ts
│
└── output/
    ├── markdown.ts
    ├── latex.ts
    └── citations.ts
```

---

## 34. Final Architectural Rule Set

The architecture should preserve these invariants:

1. The user interacts with one Loop session.
2. Specialized agents run in isolated internal threads.
3. The runtime controls state transitions.
4. Agents communicate primarily through persisted artifacts.
5. Research precedes writing.
6. Writers only cite registered sources.
7. Writers invoke the required humanizer skill before writing-review.
8. Humanizer preserves supported claims, required format, and citation markers.
9. Reviewers judge but do not mutate accepted output.
10. Only the orchestrator/runtime commits approved sections.
11. Sections may run concurrently when dependencies allow.
12. Every loop is bounded.
13. Global review occurs after assembly.
14. Global revisions reopen only affected sections.
15. Final output is generated deterministically from approved content.
16. The entire run can be paused, inspected, resumed, or cancelled from one control surface.

---

## 35. End-State Architecture

The intended finished product is not simply a chain of prompts.

It is a local academic workflow engine with:

```text
one user session
+ deterministic orchestration
+ isolated Codex agents
+ persistent state
+ structured evidence
+ review gates
+ dependency-aware concurrency
+ selective revision
+ deterministic document assembly
```

That combination is what turns Loop from a prompt wrapper into a real agent orchestration system.


## 19. Assignment-Local Execution Model

Loop should not require a global project registry to function. The directory hierarchy belongs to the user; Loop simply operates at the assignment leaf.

Example user hierarchy:

```text
Desktop/
└── 3rd Year/
    ├── CISC321/
    │   ├── Assignment 1/
    │   ├── Assignment 2/
    │   └── Project/
    ├── MATH221/
    │   └── Assignment 1/
    └── CISC324/
        └── Essay/
```

Each leaf can independently contain `.loop/` state and `output/` artifacts.

This architecture provides:

- isolation between classes
- isolation between assignments
- portable assignment folders
- simple Git compatibility
- easy backup/archive behavior
- trivial resume semantics
- no dependence on a centralized Loop workspace

A future global command such as `loop recent` may maintain only lightweight metadata pointing to known assignment roots. It should not move, duplicate, or centralize assignment contents.
