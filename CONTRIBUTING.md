# Contributing to Fab7

Fab7 is intentionally small. Keep each change tied to one proof-core outcome
and avoid adding adjacent frameworks, compatibility layers, or distribution
machinery.

## Development setup

Requirements are Git, Python 3.11 or newer, and uv. Version `0.11.32` is the
tested uv recommendation.

```bash
git clone https://github.com/fab7hq/fab7.git
cd fab7
uv sync --locked
```

## Required local checks

```bash
uv lock --check --no-config
uv run --locked python -m pytest
uv run --locked python -m compileall -q core/fab7
uv build
git diff --check
git status --short
```

When package behavior changes, install the built wheel into a disposable uv
tool root and smoke the console script outside the checkout. When static host
assets change, validate their native manifests and skills without installing
them into a live host unless that mutation is separately authorized.

Pull requests should explain the exact subject, checks, and observed results.
Do not include credentials, private source, generated environments, build
artifacts, or unrelated cleanup.
