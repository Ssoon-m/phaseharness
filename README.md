# phaseloop

Portable five-phase agent workflow for Claude Code and Codex.

phaseloop installs a provider-neutral harness into a repository. It turns one
concrete repository request into durable task state, implementation phases, and
evaluation so the workflow does not depend on one long conversation.

## Install

Open Claude Code or Codex in the target repository and ask:

```text
Install phaseloop from this installer document:
https://github.com/Ssoon-m/phaseloop/blob/main/installer/install-harness.md
```

The installer copies the canonical harness, generates Claude/Codex bridges,
creates starter project docs, initializes local task state, and runs smoke
verification.

Install from the directory that should own the workflow state. In a monorepo,
that can be the repo root or a specific app/package directory.

## Run A Task

Use the installed skill:

```text
Use the phaseloop skill to implement <request> with max attempts 3 and commit mode none.
```

`max attempts` controls the retry budget for each workflow session or build
phase. `commit mode` controls whether phaseloop creates git commits.
If either value is omitted, the skill asks once before using a default.
Before the headless runner starts, the skill clarifies the request in the
current conversation and records the resulting questions, decisions, and done
conditions as the first task artifact.

To force a specific runtime, include it in the skill request, for example
`using Claude` or `using Codex`. Otherwise phaseloop uses the configured
default.

## Commit Modes

phaseloop defaults to `none`.

- `none`: leave changes uncommitted.
- `final`: create one product commit after evaluation passes or warns.
- `phase`: ask the commit skill to commit each completed generate phase using
  phase context. Evaluation stays local and does not create an empty validation
  commit.

Product commits exclude phaseloop task artifacts by default. Runtime task state
under `tasks/` stays local unless you explicitly choose to include it.
When there are no product changes to commit, the commit step succeeds without
creating an empty commit.

The commit script checks task completion, evaluation status, HEAD movement, and
pre-existing dirty paths before creating a commit.

To commit the latest completed phaseloop result manually:

```bash
python3 scripts/commit-result.py
```

To commit a specific task:

```bash
python3 scripts/commit-result.py <task-dir>
```

To intentionally include phaseloop state:

```bash
python3 scripts/commit-result.py <task-dir> --include-harness-state
```

## How It Works

phaseloop runs one request through five logical phases:

```text
clarify -> context gather -> plan -> generate -> evaluate
```

Phase meanings:

- `clarify`: convert the request into scope, decisions, assumptions, non-goals,
  and done conditions.
- `context gather`: collect the repository facts needed for the clarified task:
  relevant files, patterns, constraints, risks, and validation commands.
- `plan`: turn the clarified task and context into ordered implementation phases
  with concrete acceptance criteria.
- `generate`: execute the planned phases, validate when possible, and record the
  result without reopening clarification or planning.
- `evaluate`: independently check the completed work against done conditions and
  acceptance criteria, then report pass, warn, or fail.

By default, phaseloop runs clarify in the current conversation so the agent can
ask the user material questions before code is planned. It then groups context
gather and plan into one headless analysis session, followed by separate build
and evaluation sessions:

```text
main session: clarify
analysis: context gather + plan
build: planned implementation phases
evaluate: independent verification
```

This keeps requirement ambiguity in the user-facing conversation, avoids
restarting a provider session for every later logical phase, and keeps final
evaluation separate from the implementation session. This is the default
`balanced` strategy.

## Where State Lives

Task state is stored under `tasks/` and is gitignored by default in installed
repositories.

Canonical harness files live under `.agent-harness/`. Claude and Codex runtime
bridges are generated from that canonical source.

Edit `.agent-harness/` when changing the harness. Generated bridge files under
`.claude/`, `.agents/`, and `.codex/` should be treated as runtime output.

## Development

Run local verification:

```bash
python3 tests/smoke_install.py
python3 -m py_compile core/scripts/*.py core/.agent-harness/providers/*.py tests/smoke_install.py
```

For implementation details, see `SPEC.md` and `spec/`.
