---
description: Initialize Cuff at the current Git worktree root.
allowed-tools: Bash(cuff:*)
---

Run exactly one `cuff init --json` from the current Git worktree root and
return its JSON result. Do not create, edit, migrate, or remove `.fab7/cuff`
paths directly.
