# Loop — Project Plan

## 1. Project Goal

Loop is a local, subscription-backed multi-agent orchestration system for completing structured school assignments from a single command or conversation.

Loop is designed to run **inside the assignment's existing folder** rather than inside a separate Loop project directory. The user's normal school folder structure remains the source of truth. For example:

```text
Desktop/
└── 3rd Year/
    └── CISC321/
        └── Assignment 1/
            └── loop runs here
```

The user provides an assignment prompt, outline, rubric, source links, historical grade feedback, constraints, and output requirements from that folder. Loop decomposes the work, runs section-level agent workflows, validates intermediate outputs, assembles the final artifact, and performs a whole-document review before completion.

Assignment guidance is grouped under an optional `outline/` directory. The
directory may contain an assignment outline and one or more rubrics. Historical
grades or professor feedback belong in `sources/` alongside the required
`links.md`; those optional files may be PDF, DOCX, or text. File names under
`outline/` are not part of the contract, and PDFs are valid guidance inputs.
Loop indexes every outline file and classifies likely rubric and legacy history
files for agent routing. When historical feedback is available, planning,
writing, and review agents extract supported reasons marks were lost and turn
them into concrete do/not-do checks; current assignment requirements remain
authoritative.

The intended interaction is simple:

```bash
$ loop "Complete the assignment in assignment.md using the supplied sources. Output Markdown."
```

The user interacts with one top-level session. Internally, Loop coordinates multiple Codex agents using the user's existing ChatGPT/Codex subscription rather than requiring an OpenAI API key.

---

## 2. Core Product Principles

1. **One human session, many machine sessions**  
   The user should not need to manually switch between planner, researcher, writer, or reviewer agents.

2. **Deterministic orchestration around probabilistic agents**  
   Code controls sequencing, state, retries, dependencies, file writes, acceptance criteria, and termination. Models handle reasoning-heavy tasks.

3. **Section-level execution**  
   Large assignments are decomposed into sections. Each section is planned, reviewed, researched, written, reviewed again, and only then accepted.

4. **Evidence before prose**  
   Research and citation evidence are gathered before writing. Writers should not invent or casually infer citations while drafting.

5. **Review gates before document mutation**  
   Reviewers judge work but do not directly mutate the final artifact. The orchestrator commits approved outputs.

6. **Persistent state**  
   Every run must be resumable after interruption, failure, or manual pause.

7. **Model effort should match task difficulty**  
   High-effort reasoning is reserved for planning, writing, and review. Mechanical tasks should use lower effort where possible.

---

## 3. Primary User Flow

### Folder Model

Loop does not require users to move schoolwork into a dedicated application workspace. The assignment directory itself is the workspace root.

Example:

```text
Desktop/
└── 3rd Year/
    ├── CISC321/
    │   ├── Assignment 1/
    │   │   ├── assignment.md
    │   │   ├── outline/
    │   │   │   ├── assignment-outline.pdf
    │   │   │   └── rubric.pdf
    │   │   ├── sources/
    │   │   │   ├── links.md
    │   │   │   └── past-grade.pdf
    │   │   └── loop runs here
    │   └── Assignment 2/
    └── MATH221/
        └── Assignment 1/
```

The year and course folders are organizational only. Loop operates on the **current assignment directory** and should not read sibling assignments or other courses unless explicitly instructed.

### Input

An assignment folder may contain:

```text
Assignment 1/
├── assignment.md
├── outline/
│   ├── assignment-outline.pdf
│   └── rubric.pdf
├── sources/
│   ├── links.md
│   └── past-grade.pdf
│   ├── links.md
│   ├── past-grade.pdf
│   └── professor-feedback.docx
└── loop.config.json        # optional
```

The user opens a terminal in the assignment folder and starts the system with:

```bash
cd "Desktop/3rd Year/CISC321/Assignment 1"
loop run .
```

or:

```bash
loop "Use the assignment and sources in this directory. Complete the paper and output Markdown."
```

### Execution

Loop should:

1. Parse assignment requirements.
2. Identify required sections and dependencies.
3. Create a global task graph.
4. Execute each section through its local agent pipeline.
5. Assemble approved sections.
6. Run a whole-document review.
7. Reopen affected sections if required.
8. Produce the final requested artifact.

### Output

Initial supported output types:

- Markdown
- LaTeX

By default, completed artifacts should be written inside an `output/` directory within the current assignment folder.

Future output types may include DOCX or PDF via deterministic render/export tooling.

---


## 3.1 Workspace Boundary Rules

Loop must treat the current working directory as a hard workspace boundary by default.

Rules:

- The directory passed to `loop run` becomes the assignment root.
- Loop may recursively inspect files and folders inside that root.
- Loop must not automatically inspect parent directories, sibling assignments, or other course folders.
- Any access outside the assignment root requires an explicit path or user instruction.
- All Loop-generated state should remain local to the assignment root.
- The user's original assignment files should not be overwritten unless explicitly requested.

Loop-managed files should live under a hidden local directory:

The generated outline index records every file under `outline/`, including PDF
inputs and categorized past-mark or professor-feedback references. The source
manifest requires `sources/links.md`, extracts its HTTP(S) links into the source
registry, and passes optional PDF, DOCX, or text files in `sources/` as historical
grade guidance rather than citable sources.

```text
Assignment 1/
├── assignment.md
├── outline/
│   ├── assignment-outline.pdf
│   └── rubric.pdf
├── sources/
│   ├── links.md
│   └── past-grade.pdf
├── .loop/
│   ├── state.json
│   ├── global-plan.json
│   ├── source-index.json
│   ├── evidence.json
│   ├── sections/
│   ├── reviews/
│   └── logs/
└── output/
    └── final.md
```

This makes each assignment self-contained, portable, resumable, and easy to delete or archive independently.

---

## 4. Agent Roles

### 4.1 Orchestrator

**Recommended model:** GPT-5.6 Luna xHigh

Responsibilities:

- Interpret the overall assignment.
- Identify sections and dependencies.
- Create the global execution graph.
- Decide which sections can run in parallel.
- Launch and supervise section pipelines.
- Track status and failures.
- Handle retry limits.
- Commit approved sections.
- Trigger final assembly and global review.
- Manage revision routing.
- Determine final completion.

The orchestrator should reason about workflow, not perform all content work itself.

---

### 4.2 Section Planner

**Recommended model:** GPT-5.6 Luna High

Responsibilities:

- Define the purpose of one section.
- Determine the claims that section must establish.
- Identify evidence requirements.
- Define section structure.
- Allocate approximate word count.
- Note dependencies on earlier sections.
- Produce a structured section plan.

The planner does not write final prose.

---

### 4.3 Reviewer

**Recommended model:** GPT-5.6 Luna xHigh

The same reviewer role may evaluate both plans and written drafts, using different review schemas.

#### Plan Review

Checks:

- alignment with the assignment
- logical structure
- evidence requirements
- missing claims
- overlap with other sections
- scope and word allocation

Returns:

- `APPROVE`
- `REVISE`

#### Writing Review

Checks:

- factual support
- citation validity
- argument quality
- adherence to approved plan
- structure
- clarity
- formatting
- assignment requirements
- unsupported claims

Returns structured issues rather than directly rewriting the section.

---

### 4.4 Researcher

**Recommended model:** GPT-5.6 Luna High, escalating to xHigh when needed

Responsibilities:

- Read `sources/links.md` and inspect its listed web sources.
- Read optional source-folder PDF, DOCX, and text files for past-grade guidance.
- Search the web when permitted to open and verify the listed links.
- Extract evidence for approved claims.
- Capture citation metadata.
- Record page/section locations where possible.
- Detect conflicting evidence.
- Distinguish verified evidence from inference.
- Produce structured research artifacts.

The researcher should not write the final section prose.

---

### 4.5 Writer

**Recommended model:** GPT-5.6 Luna xHigh

Responsibilities:

- Read the approved plan.
- Read verified evidence.
- Produce polished section prose.
- Follow requested citation style.
- Respect section word targets.
- Address reviewer feedback on revision cycles.
- Invoke the `humanizer` skill in embedded mode after drafting and before
  writing the declared draft artifact.
- Preserve every supported claim, required heading and format, and all
  registered `[S##]` citation markers through the humanizer pass.

The writer should cite only sources present in the structured source/evidence
store. The humanizer is a required writer substep, not a separate agent or
state-machine stage. It edits prose only and does not research or add claims.

---

### 4.6 Global Reviewer

**Recommended model:** GPT-5.6 Luna xHigh

Runs after section assembly.

Checks document-level concerns that cannot be evaluated reliably in isolation:

- thesis consistency
- argument progression
- section transitions
- duplication
- contradictions
- tone consistency
- introduction/conclusion alignment
- assignment-wide requirements
- bibliography completeness
- citation consistency
- formatting consistency
- total word count

The global reviewer returns either `PASS` or a structured list of affected sections and required revisions.

---

## 5. Section Pipeline

Every section should follow this lifecycle:

```text
PLAN
  ↓
PLAN REVIEW
  ↓
RESEARCH
  ↓
WRITE
  ↓
WRITING REVIEW
  ↓
APPROVE / REVISE
```

Detailed behavior:

1. Section planner creates `plan.json`.
2. Reviewer evaluates the plan.
3. If rejected, feedback returns to planner.
4. Once approved, researcher gathers evidence.
5. Writer creates the draft, invokes the required `humanizer` skill, verifies
   claim and citation-marker preservation, and writes `draft.md` or the
   configured intermediate representation.
6. Reviewer evaluates the humanized draft.
7. If rejected, issues return to writer, who reruns the humanizer pass after
   revising.
8. Once approved, orchestrator commits the section.

No reviewer should directly modify the final document.

---

## 6. Global Pipeline

```text
USER INPUT
   ↓
ORCHESTRATOR
   ↓
GLOBAL TASK GRAPH
   ↓
SECTION PIPELINES
   ↓
APPROVED SECTIONS
   ↓
DOCUMENT ASSEMBLY
   ↓
GLOBAL REVIEW
   ↓
PASS ───────────────→ FINAL OUTPUT
   │
   └── REVISE
         ↓
   affected sections
         ↓
   section pipeline
         ↓
   reassemble
         ↓
   global review
```

---

## 7. Parallelism

Sections should not automatically run sequentially.

The orchestrator should build a dependency graph such as:

```text
Background
   ↓
┌───────────────┐
↓               ↓
Argument    Counterargument
└───────┬───────┘
        ↓
     Analysis
        ↓
   Conclusion
        ↓
  Introduction
```

Independent sections may execute concurrently.

Parallel execution should be bounded to protect subscription usage and machine resources.

Suggested configuration:

```json
{
  "max_parallel_sections": 2,
  "max_parallel_researchers": 3
}
```

---

## 8. Workspace Layout

Suggested runtime structure:

```text
project/
├── assignment.md
├── outline/
│   ├── assignment-outline.pdf
│   └── rubric.pdf
├── sources/
│
├── .loop/
│   ├── state.json
│   ├── assignment.json
│   ├── global-plan.json
│   ├── task-graph.json
│   ├── source-index.json
│   ├── evidence.json
│   │
│   ├── sections/
│   │   ├── 01-background/
│   │   │   ├── plan.json
│   │   │   ├── plan-review.json
│   │   │   ├── research.json
│   │   │   ├── draft.md
│   │   │   └── review.json
│   │   │
│   │   └── 02-argument/
│   │       └── ...
│   │
│   ├── reviews/
│   │   └── global-review.json
│   │
│   └── logs/
│
└── output/
    ├── final-draft.md
    └── final.md
```

---

## 9. Structured Evidence System

Research should be stored independently from prose.

Example:

```json
{
  "source_id": "S03",
  "title": "Example Paper",
  "authors": ["Jane Smith"],
  "year": 2024,
  "type": "journal",
  "url": "https://example.com",
  "evidence": [
    {
      "id": "S03-E01",
      "claim": "Claim supported by this source",
      "location": "p. 14",
      "paraphrase": "Structured evidence summary",
      "confidence": "high"
    }
  ]
}
```

Writers should cite internal source IDs during generation when practical. Citation rendering can then be normalized deterministically.

---

## 10. Review Schemas

Plan review example:

```json
{
  "decision": "APPROVE",
  "issues": [],
  "missing_evidence": [],
  "scope_issues": []
}
```

Writing review example:

```json
{
  "decision": "REVISE",
  "score": 84,
  "critical_issues": [
    {
      "type": "UNSUPPORTED_CLAIM",
      "location": "paragraph-3",
      "severity": "high",
      "description": "The cited source does not support the claim.",
      "required_action": "Replace the citation or revise the claim."
    }
  ],
  "citation_issues": [],
  "formatting_issues": [],
  "argument_issues": []
}
```

---

## 11. Termination Rules

Every loop requires explicit limits.

Suggested defaults:

```text
max_plan_revisions_per_section = 2
max_writing_revisions_per_section = 3
max_global_revision_cycles = 2
max_agent_failures = 3
```

A section is accepted only when:

```text
plan approved
AND
research completed
AND
writing review approved
```

The entire assignment is complete only when:

```text
all required sections approved
AND
global review passed
AND
output artifact generated
```

---

## 12. CLI Experience

Core commands:

```bash
loop run .
loop resume .
loop pause
loop status
loop agents
loop log <agent-or-section>
loop cancel
```

Example status:

```text
Research Paper

Planning        ✓
Research        ✓
Section 1       ✓
Section 2       reviewing
Section 3       writing
Conclusion      pending
Global review   pending
```

The user should always interact with one top-level session.

---

## 13. Configuration

Suggested `loop.config.json`:

```json
{
  "output": "markdown",
  "citation_style": "APA",
  "models": {
    "orchestrator": {
      "model": "gpt-5.6-luna",
      "effort": "xhigh"
    },
    "planner": {
      "model": "gpt-5.6-luna",
      "effort": "high"
    },
    "researcher": {
      "model": "gpt-5.6-luna",
      "effort": "high"
    },
    "writer": {
      "model": "gpt-5.6-luna",
      "effort": "xhigh"
    },
    "reviewer": {
      "model": "gpt-5.6-luna",
      "effort": "xhigh"
    }
  },
  "limits": {
    "max_parallel_sections": 2,
    "max_plan_revisions": 2,
    "max_writing_revisions": 3,
    "max_global_revisions": 2
  }
}
```

Exact model identifiers and supported effort strings should be resolved against the installed Codex runtime at implementation time.

---

## 14. Development Roadmap

### Phase 1 — Runtime Foundation

Build the local orchestration core.

- CLI entry point
- project workspace discovery
- configuration parser
- run ID and persistent state
- Codex process/SDK adapter
- structured agent invocation
- logging
- pause/resume
- failure handling

Success criterion:

A single agent can be invoked through Loop, write a structured result, and resume from persisted state.

---

### Phase 2 — Basic Section Loop

Implement:

```text
Planner → Reviewer → Writer → Reviewer
```

- section state machine
- structured plan schema
- review schema
- retry routing
- approved section commit

Success criterion:

One manually supplied section can complete its review loop autonomously.

---

### Phase 3 — Research Layer

Add the researcher between plan review and writing.

- `sources/links.md` ingestion
- source registry for allowlisted web links
- historical grade-feedback inputs (not citable)
- evidence records
- citation metadata
- external research permissions
- source/evidence validation

Success criterion:

The writer can produce a section using only verified evidence supplied by the research layer.

---

### Phase 4 — Assignment Orchestrator

Add global decomposition.

- assignment parser
- global planner
- section discovery
- dependency graph
- dependency-aware scheduling
- bounded parallel execution

Success criterion:

Loop can accept a complete assignment and automatically generate and execute section pipelines.

---

### Phase 5 — Document Assembly

- approved section registry
- deterministic section ordering
- Markdown output
- LaTeX output
- bibliography generation
- citation normalization
- word-count validation

Success criterion:

Loop produces a complete assembled artifact from approved sections.

---

### Phase 6 — Global Review Loop

- full-document reviewer
- cross-section issue detection
- affected-section routing
- reassembly
- global revision limits

Success criterion:

The system can detect document-level problems and selectively reopen only the relevant sections.

---

### Phase 7 — User Control Surface

Improve the one-window experience.

- live event stream
- agent/section status
- `/status`
- `/agents`
- `/pause`
- `/resume`
- `/cancel`
- manual user intervention
- mid-run requirement changes

Success criterion:

A user can supervise the entire assignment without entering individual agent sessions.

---

### Phase 8 — Reliability and Cost Controls

- usage accounting
- context trimming
- artifact-based communication
- model effort routing
- concurrency limits
- timeout policies
- duplicate-work prevention
- idempotent retries
- checkpointing

Success criterion:

Long assignments can run without uncontrolled usage, runaway loops, or state corruption.

---

### Phase 9 — Production Hardening

- test suite for state transitions
- malformed-agent-output recovery
- schema validation
- interrupted-run recovery
- source provenance tests
- citation integrity tests
- sandbox/security controls
- configuration migration
- telemetry/logging controls

Success criterion:

Loop is robust enough to trust on real coursework without requiring manual babysitting.

---

## 15. Non-Goals

Loop should not initially become:

- a general-purpose autonomous computer agent
- an LMS replacement
- a note-taking platform
- a vector-database-heavy RAG framework
- a full GUI-first product
- a framework with dozens of arbitrary agent personas

The product is strongest when focused on one workflow:

> Turn a structured academic assignment into a controlled, review-gated, evidence-backed multi-agent execution graph.

---

## 16. Definition of Done

The first complete product version is successful when a user can:

1. Create a project directory.
2. Add an assignment, rubric, outline, and sources.
3. Run one command.
4. Watch a single orchestrated session.
5. Pause or inspect the run at any point.
6. Allow Loop to plan, research, write, review, and revise each section.
7. Receive one final Markdown or LaTeX document.
8. Inspect exactly how each section was planned, researched, written, and approved.
9. Resume interrupted runs without losing progress.
10. Complete the workflow using Codex subscription-backed agent execution rather than requiring an API key.


## 13. Local Folder Execution Requirements

The finished product should support a natural university directory layout without requiring imports or project creation.

Canonical usage:

```bash
cd ~/Desktop/3rd\ Year/CISC321/Assignment\ 1
loop run .
```

or, from elsewhere:

```bash
loop run "~/Desktop/3rd Year/CISC321/Assignment 1"
```

Loop should resolve that directory as `workspace_root` and persist it in run state using an absolute normalized path.

Example runtime state:

```json
{
  "workspace_root": "C:/Users/Alex/Desktop/3rd Year/CISC321/Assignment 1",
  "loop_dir": "C:/Users/Alex/Desktop/3rd Year/CISC321/Assignment 1/.loop",
  "output_dir": "C:/Users/Alex/Desktop/3rd Year/CISC321/Assignment 1/output"
}
```

No global database is required for core functionality. A small optional global index may later track recent assignments, but assignment content and agent state remain local to each assignment directory.
