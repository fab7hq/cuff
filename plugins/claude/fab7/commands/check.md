---
description: Check fresh Fab7 evidence for one explicit work item.
argument-hint: --work-item ID [--base REF] [--head REF]
allowed-tools: Bash(fab7:*)
---

Treat `$ARGUMENTS` as the caller's exact check arguments. Require an explicit
work item, then run `fab7 check --json $ARGUMENTS` from the initialized Git
root. Report the result without changing Git or Fab7 records.
