# Cuff GitHub Action

The composite Action installs a selected released `cuff-cli` package with uv
and delegates the decision to the public `cuff check` command. It contains no
second readiness implementation, initialization, native build, or host plugin
logic.

The consumer must track an initialized `.fab7/cuff/project.json`, preserve full Git
history, and pass the work item and comparison refs explicitly:

```yaml
- uses: actions/checkout@v6
  with:
    fetch-depth: 0

- uses: fab7hq/cuff/action@v0.1.0
  with:
    version: "0.1.0"
    working-directory: "."
    work-item: "task-1"
    base: ${{ github.event.pull_request.base.sha }}
    head: ${{ github.event.pull_request.head.sha }}
```

The action requires the released package to be available to uv. Replace the
version and action revision together for another reviewed release.
