---
description: Atomically record a Cuff claim and verifier observation.
argument-hint: --work-item ID --summary TEXT SUBJECT -- COMMAND [ARGS...]
allowed-tools: Bash(cuff:*)
---

Treat `$ARGUMENTS` as the caller's exact Cuff seal arguments. Require an
explicit work item, summary, complete subject, and literal verifier argv. Run
one `cuff seal --json $ARGUMENTS` from the initialized Git root and accept only
a matching JSON receipt. Do not edit Cuff records directly.
