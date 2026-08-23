---
description: Check fresh Cuff evidence for one explicit work item.
argument-hint: --work-item ID [--base REF] [--head REF]
allowed-tools: Bash(cuff:*)
---

Treat `$ARGUMENTS` as the caller's exact check arguments. Require an explicit
work item, then run `cuff check --json $ARGUMENTS` from the initialized Git
root. Report the result without changing Git or Cuff records.
