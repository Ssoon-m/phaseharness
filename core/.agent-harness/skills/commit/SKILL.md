---
name: commit
description: Commit harness artifacts with focused staging and iteration markers.
---

# Commit

Use this skill when a harness step needs a focused commit.

Rules:

- Stage only files owned by the current step.
- Do not use broad staging when unrelated work may exist.
- Include an `iter-id: <iter-id>` trailer when the step belongs to an iteration.
- Do not push.
- Do not rewrite history unless the rollback prompt explicitly requests it.
