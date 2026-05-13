# Phaseharness

Phaseharness is a file-based workflow system for large AI coding tasks.

Work proceeds through these stages:

```text
clarify -> context_gather -> plan -> generate -> evaluate
```

Instead of relying on chat history, each task keeps its progress in files:

```text
.phaseharness/runs/<run-id>/
```

This makes long tasks easier to pause, resume, inspect, and avoid duplicating.

## What It Does

Phaseharness splits large coding work into these steps:

- clarify requirements
- inspect repository structure and related files
- create independently implementable phase files
- implement one phase at a time
- evaluate the current diff against the agreed criteria

The Python state management script only reads and writes state files and prints the next prompt. It does not run a model, create subagents, edit product code, evaluate results, or run `git commit`.

## Getting Started With Phaseharness

Open your coding agent in the repository where you want to install Phaseharness, then enter:

```text
Install phaseharness from this installer document:
https://github.com/Ssoon-m/phaseharness/blob/main/installer/install-harness.md
```

## Quick Start

Ask the agent to use the workflow skill:

```text
Use `phaseharness` to implement <task>.
```

## Project Context Config

After installation, copy `.phaseharness/context.example.json` to `.phaseharness/context.json` to enable project-specific context. The example file is documentation only and is not used as active configuration.

```bash
cp .phaseharness/context.example.json .phaseharness/context.json
```

Use `context-gather.documents` for documents that affect implementation planning. Use `evaluate.documents` for documents that should guide code evaluation. Use `evaluate.rules` for evaluation rules that should be injected directly into the reviewer prompt.

Supported `priority` values:

- `required`: must be checked for relevance. Relevant missing, unreadable, or conflicting guidance is recorded as risk.
- `recommended`: considered when relevant to the request.
- `optional`: used only when clearly relevant.

Before creating a run, `phaseharness` first checks whether this worktree already has an active run. If it does, it asks you to choose:

- `resume`: bind the existing active run to the current session and continue it
- `start-new-in-worktree`: create a new git worktree and branch for a separate run
- `cancel`: do nothing

If no active run exists, `phaseharness` checks these options:

- `loop count`: maximum number of `generate -> evaluate` cycles
- `commit mode`: one of `none`, `phase`, `final`

Defaults:

```text
loop count: 2
commit mode: none
```

After confirmation, `phaseharness` creates a run, binds it to the current provider session, and starts the first stage from the run files.

## Parallel Runs

One worktree has at most one active phaseharness run. Parallel phaseharness work uses git worktrees, not multiple active runs in the same working tree.

```bash
python3 .phaseharness/bin/phaseharness-worktree.py create --request "<request>" --json
```

The default naming is:

- run/worktree name: `YYYYMMDD-HHMMSS-<task-slug>`
- branch: `phaseharness/<name>`
- path: `<repo-parent>/<repo-name>.worktrees/<name>`

Start a new Codex/Claude session in the new worktree before starting the new run, and use the returned `run_id` when creating that run.

## Manual Skills

You can run each stage directly:

- `clarify`: organize requirements, success criteria, scope, non-goals, assumptions, and open questions.
- `context-gather`: collect repository structure, relevant files, existing patterns, constraints, risks, and validation commands.
- `plan`: create `artifacts/plan.md` and self-contained `phases/phase-NNN.md` files. Split feature slices, long-running work, work with different validation criteria, and work with different risk profiles into separate phases.
- `generate`: implement exactly one existing phase file. Do not use it as a general implementation command.
- `evaluate`: verify whether the current diff satisfies the task criteria.
- `commit`: create a meaningful commit when the user explicitly requests it or when Phaseharness creates a commit prompt.

Manual skill runs perform one stage and stop. They do not continue automatically through the Stop hook.

## Phase Splitting Criteria

`plan` prioritizes independent implementation and independent review over minimizing the number of phases.

Split phases when:

- a user-visible feature or behavior can be completed independently
- the work is likely to take a long time or touch many files
- the work has a different risk profile, such as data structure changes, state handling, UI behavior, external integration, or test infrastructure
- validation commands or acceptance criteria differ
- a preparatory step reduces uncertainty for later work
- target files, allowed changes, or forbidden changes would otherwise become too broad

Avoid splitting only by file. Each phase should be implementable by a fresh implementer without chat memory, and reviewable by a fresh reviewer using only the phase file and diff.

## Automatic Runs

Only `phaseharness` creates automatic runs. The Stop hook can continue only automatic runs.

The Stop hook calls only this command:

```bash
python3 .phaseharness/bin/phaseharness-state.py next --require-auto --reprompt-running --require-session-binding --json
```

The Stop hook does not run a model, create a subagent, edit files, evaluate, or commit. It only asks the state management script for the next prompt and passes that prompt to the current session.

The Stop hook is a no-op if the hook session id is missing, the run has no binding, or the hook session id does not match the run's bound session id.

If a stage remains `running`, `--reprompt-running` returns a prompt to re-enter the same stage instead of starting new work.

## Roles

The current conversation session controls the run.

- `clarify`, `context-gather`, and `plan` are performed by the current conversation session.
- `generate` delegates exactly one phase file to one new implementation subagent.
- `evaluate` delegates to one new review subagent.
- Subagents do not call state commands.
- Subagents do not change run state.
- Subagents do not commit.
- Subagents report the assigned result and stop. The current conversation session closes the subagent session when the provider supports it.
- The current conversation session writes artifacts, reviews subagent results, updates state, and handles commit prompts.

Phaseharness does not predefine subagents during installation. The `generate` and `evaluate` skills create new subagent requests when those stages run.

## Run Files

Each run has these files:

```text
.phaseharness/runs/<run-id>/
  run.json
  artifacts/
    clarify.md
    context.md
    plan.md
    generate.md
    evaluate.md
  phases/
    phase-001.md
    phase-002.md
```

`run.json` records:

- current stage
- manual or automatic mode
- loop count
- commit mode
- stage statuses
- generate phase queue
- evaluate result
- commit prompt results
- files that were already changed when the run started

## State Management Commands

Create an automatic run:

```bash
python3 .phaseharness/bin/phaseharness-state.py start \
  --mode auto \
  --request "<request>" \
  --loop-count 2 \
  --commit-mode none \
  --json
```

Check status:

```bash
python3 .phaseharness/bin/phaseharness-state.py status --json
```

Create the next continuation prompt:

```bash
python3 .phaseharness/bin/phaseharness-state.py next --require-auto --reprompt-running --require-session-binding --json
```

Resume and rebind an active run to the current session:

```bash
python3 .phaseharness/bin/phaseharness-state.py resume --json
```

Create a parallel worktree:

```bash
python3 .phaseharness/bin/phaseharness-worktree.py create --request "<request>" --json
```

Record a stage status:

```bash
python3 .phaseharness/bin/phaseharness-state.py set-stage clarify completed --run-id <run-id>
```

Record a generate phase status:

```bash
python3 .phaseharness/bin/phaseharness-state.py set-generate-phase phase-001 completed --run-id <run-id>
```

Record a commit prompt result:

```bash
python3 .phaseharness/bin/phaseharness-state.py set-commit phase-001 committed --run-id <run-id>
python3 .phaseharness/bin/phaseharness-state.py set-commit final no_changes --run-id <run-id> --message "no eligible changes to commit"
```

## Commit Mode

- `none`: do not create commit prompts.
- `phase`: request a commit whenever a generate phase completes.
- `final`: request one final commit when `evaluate` is `pass` or `warn`.

Commit prompts include:

- run id
- commit key
- commit mode
- files eligible for commit
- files skipped because they were already changed before the run started
- runtime files and tool connection files skipped by default
- required `set-commit` follow-up command

Only `commit` should run the actual git commit. The commit message should describe the real change, not merely state that a phase finished.

## Safety Rules

Phaseharness separates workflow control from execution.

- `phaseharness-state.py` only manages run files and prompts.
- `phaseharness-hook.py` is a Stop hook wrapper.
- Stop hooks do nothing unless an automatic run is active and bound to the current session id.
- Manual skill runs do not continue automatically.
- Parallel automatic runs use separate git worktrees.
- Runtime files and tool connection files are excluded from commit prompts.
- Files that were already changed when a run started are excluded from commit prompts.

## Smoke Check

After installation, verify with:

```bash
python3 .phaseharness/bin/phaseharness-state.py --help
python3 .phaseharness/bin/phaseharness-hook.py --help
python3 .phaseharness/bin/phaseharness-sync-bridges.py --help
python3 .phaseharness/bin/phaseharness-worktree.py --help
python3 -m py_compile .phaseharness/bin/*.py
python3 .phaseharness/bin/phaseharness-state.py next --require-auto --reprompt-running --require-session-binding --json
```

When no run is active, the expected output includes:

```json
{ "action": "none" }
```
