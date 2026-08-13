---
name: check
description: Check fresh Git-anchored Fab7 evidence for one explicit work item.
---

Require the work item explicitly. Run `fab7 check --work-item ID --json` from
the initialized Git root, adding explicit `--base` and `--head` only when the
caller supplied them. Report the returned PASS or errors without changing Git
or Fab7 records.
