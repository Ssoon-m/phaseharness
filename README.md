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

Before creating a run, `phaseharness` checks these options:

- `loop count`: maximum number of `generate -> evaluate` cycles
- `commit mode`: one of `none`, `phase`, `final`

Defaults:

```text
loop count: 2
commit mode: none
```

After confirmation, `phaseharness` creates a run and starts the first stage from the run files.

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
python3 .phaseharness/bin/phaseharness-state.py next --require-auto --reprompt-running --json
```

The Stop hook does not run a model, create a subagent, edit files, evaluate, or commit. It only asks the state management script for the next prompt and passes that prompt to the current session.

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
python3 .phaseharness/bin/phaseharness-state.py next --require-auto --reprompt-running --json
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
- Stop hooks do nothing unless an automatic run is active.
- Manual skill runs do not continue automatically.
- Runtime files and tool connection files are excluded from commit prompts.
- Files that were already changed when a run started are excluded from commit prompts.

## Smoke Check

After installation, verify with:

```bash
python3 .phaseharness/bin/phaseharness-state.py --help
python3 .phaseharness/bin/phaseharness-hook.py --help
python3 .phaseharness/bin/phaseharness-sync-bridges.py --help
python3 -m py_compile .phaseharness/bin/*.py
python3 .phaseharness/bin/phaseharness-state.py next --require-auto --reprompt-running --json
```

When no run is active, the expected output includes:

```json
{ "action": "none" }
```
