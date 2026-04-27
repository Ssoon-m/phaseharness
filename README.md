# phaseloop

Portable five-phase agent workflow for Claude Code and Codex.

phaseloop installs a provider-neutral harness into a target repository. It turns
one explicit work request into durable artifacts, task phases, implementation,
and evaluation without relying on a single conversation's memory. The current
conversation stays small while fresh headless agent sessions do the actual work.

## Install

Open Claude Code or Codex in the repository where you want phaseloop installed,
then give the agent this URL:

```text
https://github.com/Ssoon-m/phaseloop/blob/main/installer/install-harness.md
```

Tell it:

```text
Install phaseloop from this installer document.
```

The installer clones `https://github.com/Ssoon-m/phaseloop.git`, copies the
canonical core, generates Claude/Codex bridges, creates starter project docs,
and runs smoke verification.

## Start A Task

Ask the installed agent to use the skill:

```text
Use the phaseloop skill to implement <small request> with max attempts 3.
```

The skill is a thin entry point. It confirms or uses `max attempts` and
`commit mode`, then starts the headless workflow runner. If you omit either
value, the agent should ask once and use the default only after you accept it.

```bash
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "Implement <small request>" --provider codex --max-attempts 2 --session-timeout-sec 600 --commit-mode none
```

Use `--provider claude` to force Claude Code, or omit `--provider` to use the
configured default provider.

Commit mode defaults to `none`. When the skill starts, it should ask which mode
to use unless you already specified one:

- `none`: do not commit automatically
- `final`: create one commit after the whole workflow succeeds
- `phase`: commit after each completed generate phase

Examples:

```text
Use the phaseloop skill to implement <small request> with max attempts 3 and commit mode final.
Use the phaseloop skill to implement <larger request> with max attempts 3 and commit mode phase.
```

Those map to:

```bash
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "Implement <small request>" --provider codex --max-attempts 3 --session-timeout-sec 600 --commit-mode final
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "Implement <larger request>" --provider codex --max-attempts 3 --session-timeout-sec 600 --commit-mode phase
```

## How It Works

phaseloop runs one request through five phases:

```text
clarify -> context gather -> plan -> generate -> evaluate
```

- `clarify`: understand the request, done conditions, assumptions, and non-goals
- `context gather`: find the relevant docs, code, patterns, and constraints
- `plan`: create task state and implementation phase files
- `generate`: execute the planned phases
- `evaluate`: verify the result against done conditions and acceptance criteria

Each phase writes an artifact under `tasks/<task-dir>/artifacts/`. The next
phase reads those files from disk, so progress survives context loss and runtime
switches.

The default agent-session strategy is balanced:

```text
analysis session: clarify + context gather + plan
build session(s): planned implementation phases
evaluate session: independent verification
```

This avoids one large conversation containing the whole job, but it also avoids
starting a fresh agent session for every small logical phase and repeatedly
loading the same startup context.

`--max-attempts` controls how many times the analysis session, each build phase,
and the evaluate session may retry before recording an error in
`tasks/<task-dir>/index.json`. It is a retry budget, not an infinite loop count.

`--session-timeout-sec` controls how long one headless agent session or build
phase call may run before it is treated as failed and retried.

## Committing Results

phaseloop includes a `commit` skill for finished workflow results and normal
current-session git commits.

Automatic workflow commit behavior is controlled by `--commit-mode`:

- `none` is the default and leaves all changes uncommitted.
- `final` commits the latest completed task result after evaluation is `pass` or
  `warn`.
- `phase` commits completed generate phases as the workflow progresses.
  Evaluation remains local task state and does not create an empty validation
  commit.

Product commits do not include `tasks/<task-dir>/artifacts/*` by default. The
commit subject is selected from the work request or phase metadata, so the git
history says what work was done without storing phaseloop internals in each
commit. Installed target repositories also get `tasks/.gitignore`, so runtime
task directories stay local unless you explicitly choose to commit them.

To commit the latest completed phaseloop task:

```text
Use the commit skill to commit the latest phaseloop result.
```

Or run the deterministic script directly:

```bash
python3 scripts/commit-result.py
```

To commit a specific task:

```bash
python3 scripts/commit-result.py <task-dir>
```

To intentionally include phaseloop task artifacts in a commit:

```bash
python3 scripts/commit-result.py <task-dir> --include-harness-state
```

The commit script checks that the task completed, evaluation is `pass` or
`warn`, `git HEAD` did not move during the workflow, and paths that were dirty
before the workflow started are not being mixed into the commit. If the workflow
started from a dirty worktree, automatic commit will usually stop and ask for a
manual decision. For best results, start commit-mode workflows from a clean
worktree and avoid editing the same repository while they run.

## Generated State

An executed task produces files like:

```text
tasks/<task-dir>/
  index.json
  artifacts/
    01-clarify.md
    02-context.md
    03-plan.md
    04-generate.md
    05-evaluate.md
  phase0.md
  phase1.md
  analysis-output-attempt1.json
  phase0-output.json
  generate-output.json
  evaluate-output-attempt1.json
```

Runtime task state under `tasks/` is gitignored by default in installed target
repositories. It is durable local state for the agent workflow, not product
history.

The canonical harness lives under `.agent-harness/`. Runtime-specific files are
generated bridges:

```text
.agent-harness/
  skills/phaseloop/
  skills/commit/
  roles/phase-*/

.claude/skills
.claude/agents/phase-*.md
.claude/hooks/phaseloop-sync-bridges.sh
.agents/skills
.codex/agents/phase-*.toml
.codex/hooks/phaseloop-sync-bridges.sh
```

Edit canonical files under `.agent-harness/`, not generated bridge files.
Bridge sync hooks regenerate runtime bridges when `.agent-harness/` changes.
Existing Claude/Codex hooks are preserved; phaseloop only adds or updates its
own hook entries.

## Monorepos

Install phaseloop from the directory that should own the workflow state.

- Repo-wide workflow: install from the monorepo root.
- App-specific workflow: install from `apps/<app>` or the target package.

Root and app-level installs can coexist, but they are separate scopes with
separate `tasks/` state.

## Repository Layout

```text
.
├── SPEC.md
├── spec/
│   ├── PURPOSE.md
│   ├── CONTRACT.md
│   ├── PROVIDERS.md
│   └── BRIDGES.md
├── installer/
│   └── install-harness.md
├── core/
│   ├── .agent-harness/
│   ├── scripts/
│   └── templates/
└── tests/
    └── smoke_install.py
```

## Local Development

Run the local smoke test:

```bash
python3 tests/smoke_install.py
python3 -m py_compile core/scripts/*.py core/.agent-harness/providers/*.py tests/smoke_install.py
```

To test installation from a local checkout, set:

```bash
export HARNESS_SOURCE=/absolute/path/to/phaseloop
```

Then give `installer/install-harness.md` to an agent session in a temporary
target repository.
