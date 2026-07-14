# Rules of Engagement

Applies to **Claude Code**, **Codex**, and **Cursor** agents in this repository.

## Finish the task

When work changes files and the user has **not** said otherwise:

1. Commit on the current branch with a concise message (why, not what).
2. Push to `main`.

Skip commit or push only when the user explicitly opts out (`don't commit`, `no push`, etc.).

## Branches and worktrees

- **Default:** work in the primary checkout on `main`.
- **Exception:** use a separate branch or git worktree only when the user asks (e.g. worktree, feature branch, open a PR without merging).

Never force-push `main`. Never skip hooks or commit secrets.

## Submodules

When a linked repository changes: push its `main` first, then commit and push the updated submodule pointer on this repo's `main`.

## Asset generation

When creating or editing visual assets (sprites, icons, illustrations, textures, UI art):

- Use **Codex image gen**: `~/.claude/skills/codex-imagegen/imagegen.sh <output.png> "<prompt>" [reference ...]`
- Read `~/.claude/skills/codex-imagegen/SKILL.md` for the full workflow.
- Do **not** use Cursor image gen, raw DALL·E/API calls, or placeholder stubs unless the user names a different tool.
- Write outputs into the project's asset paths; follow that game's existing prompt and post-process conventions.

## How to work

- **Minimize scope** — smallest correct change; no drive-by refactors.
- **Follow skills** — when the user invokes a skill (`/implement`, `/triage`, etc.), read and follow it.
- **Shell commands** — prefix with `rtk` (see `RTK.md`).
- **Domain language** — read `CONTEXT-MAP.md` and the relevant game `CONTEXT.md` before naming domain concepts.
- **Issue tracker** — see `docs/agents/issue-tracker.md` and `docs/agents/triage-labels.md`.
