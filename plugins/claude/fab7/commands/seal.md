---
description: Atomically record a Fab7 claim and verifier observation.
argument-hint: --work-item ID --summary TEXT SUBJECT -- COMMAND [ARGS...]
allowed-tools: Bash(fab7:*)
---

Treat `$ARGUMENTS` as the caller's exact Fab7 seal arguments. Require an
explicit work item, summary, complete subject, and literal verifier argv. Run
one `fab7 seal --json $ARGUMENTS` from the initialized Git root and accept only
a matching JSON receipt. Do not edit Fab7 records directly.
