# Agents Configuration

This file documents how agents should interact with this repository.

## Agent skills

### Issue tracker

Issues live in GitHub. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage roles map to GitHub labels. See `docs/agents/triage-labels.md`.

### Domain docs

Multi-context layout with root `CONTEXT-MAP.md` pointing to per-game CONTEXT.md files. See `docs/agents/domain.md`.

## Delivery

For every completed task that changes files, commit and push the changes directly to `main`.
When a linked repository changes, push its `main` first, then commit and push the updated
submodule pointer on this parent repository's `main`.

@RTK.md
