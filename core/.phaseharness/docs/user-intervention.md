# User Intervention

This file records work the agent harness must not perform autonomously.

Examples:

- production deployment
- credential creation
- billing or paid account changes
- data deletion
- external approval workflows

When a task requires one of these actions, the harness should record the need and stop instead of asking in headless mode.
