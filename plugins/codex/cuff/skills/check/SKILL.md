---
name: check
description: Check fresh Git-anchored Cuff evidence for one explicit work item.
---

Require the work item explicitly. Run `cuff check --work-item ID --json` from
the initialized Git root, adding explicit `--base` and `--head` only when the
caller supplied them. Report the returned PASS or errors without changing Git
or Cuff records.
