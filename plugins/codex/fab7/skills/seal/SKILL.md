---
name: seal
description: Atomically record one Fab7 claim and caller-selected verifier observation.
---

Require an explicit work item, summary, complete subject, and literal verifier
argv. Run one `fab7 seal --json ... -- COMMAND [ARGS...]` from the initialized
Git root. Accept only a JSON receipt whose claim, evidence, work item, and
subject digest match the request. Do not edit Fab7 records directly.
