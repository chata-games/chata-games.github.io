# Agents Configuration

This file documents how agents should interact with this repository.

## Agent skills

### Issue tracker

Issues live in GitHub. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage roles map to GitHub labels. See `docs/agents/triage-labels.md`.

### Domain docs

Multi-context layout with root `CONTEXT-MAP.md` pointing to per-game CONTEXT.md files. See `docs/agents/domain.md`.

## Rules of engagement

Canonical doc: `docs/agents/rules-of-engagement.md`. Applies to Claude Code, Codex, and Cursor.

**Default delivery:** when a task changes files and the user has not opted out, commit and push to `main`. Work on `main` in the primary checkout unless the user asks for a separate branch or worktree.

**Assets:** generate visual assets with Codex image gen (`~/.claude/skills/codex-imagegen/imagegen.sh`), not Cursor image gen or raw API stubs.

**Submodules:** push the linked repo's `main` first, then commit and push the updated pointer here.

@RTK.md
