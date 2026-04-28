# Providers

Providers isolate runtime-specific invocation details from the harness lifecycle.

The orchestrators must not know how Claude Code or Codex is invoked. They only call provider methods and read state files.

The default workflow uses balanced session boundaries:

- main-session clarify before provider sessions start
- one analysis provider session for context gather and plan
- one or more build provider sessions for implementation phase files
- one evaluate provider session for independent verification

Providers may reload runtime startup context for each provider session. The
balanced strategy avoids doing that for every small logical phase while keeping
user-facing clarification outside headless execution and keeping build and
evaluate context separate from analysis.

## Provider Interface

Providers must support the following concepts for prompt execution:

- `prompt`
- `cwd`
- `env`
- `timeout_sec`
- `sandbox_mode`
- `approval_policy`
- `prompt_handoff`
- `capture_json`

Providers may support role execution:

- `role_name`
- `role_prompt`
- `role_input`
- `output_schema`
- `output_path`

The practical interface is:

- `run_prompt()`: run one provider-neutral prompt session
- `run_role()`: optional helper for running one canonical role in an independent session and writing structured output

## Provider Result

Provider calls return:

```json
{
  "exit_code": 0,
  "stdout": "",
  "stderr": "",
  "failure_category": null
}
```

`failure_category` is null on success and one of the canonical failure categories on failure.

## Claude Code Policy

Claude Code headless execution currently maps to:

```bash
claude -p --dangerously-skip-permissions
```

This command shape is not the standard. The behavior is the standard:

- non-interactive execution
- no permission prompt in headless mode
- stdout/stderr captured
- `AGENT_HEADLESS=1` injected into child sessions
- runtime failures written into state files

Claude bridge files:

- `.claude/skills` from `.agent-harness/skills`
- `.claude/agents/*.md` generated from `.agent-harness/roles/*`

Native Claude subagents may be exposed for interactive convenience, but lifecycle correctness must not depend on automatic subagent selection.

## Codex Policy

Codex headless execution should map to:

```bash
codex exec --sandbox workspace-write --ask-for-approval never
```

Where supported, providers should also use:

- `--ignore-user-config`
- `--ephemeral`
- stdin prompt handoff

Codex bridge files:

- `.agents/skills` from `.agent-harness/skills`
- `.codex/agents/*.toml` generated from `.agent-harness/roles/*`

Codex subagents are explicit. The harness must not assume Codex will automatically spawn a custom agent from a description. In headless mode, phase roles are invoked explicitly by the orchestrator through the provider.

## Sandbox and Approval

Default workflow and phase execution requires `workspace-write`.

`read-only` is valid for context gathering or read-only roles, but not for generation or validation fixes. Clarify is handled by the main session before provider execution.

`on-request` is not a headless standard because it depends on approval UI. Headless runs use `never` or a runtime equivalent. If a required action is blocked, the provider records `sandbox_blocked`.

## Provider Selection

`config.toml` controls provider selection:

```toml
default_provider = "codex"
fallback_provider = "claude"
```

If both providers are available, installer may default to the current runtime, but both adapters should be installed.

If no provider is available, installer must fail preflight.
