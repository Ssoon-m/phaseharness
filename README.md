# phaseloop

Portable five-phase agent workflow for Claude Code and Codex.

phaseloop installs a provider-neutral harness into a target repository. It turns
one explicit work request into durable artifacts, task phases, implementation,
and evaluation without relying on a single conversation's memory.

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
Use the phaseloop skill to implement <small request>.
```

Or run the workflow directly:

```bash
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "Implement <small request>" --provider codex --max-attempts 2
```

Use `--provider claude` to force Claude Code, or omit `--provider` to use the
configured default provider.

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

`--max-attempts` controls how many times a phase may retry before recording an
error in `tasks/<task-dir>/index.json`.

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
  phase0-output.json
```

The canonical harness lives under `.agent-harness/`. Runtime-specific files are
generated bridges:

```text
.agent-harness/
  skills/phaseloop/
  roles/phase-*/

.claude/skills
.claude/agents/phase-*.md
.agents/skills
.codex/agents/phase-*.toml
```

Edit canonical files under `.agent-harness/`, not generated bridge files.

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
