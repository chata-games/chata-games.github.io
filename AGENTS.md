# Agents Configuration

This file documents how agents should interact with this repository.

## Agent skills

### Issue tracker

Issues live in Rohrpost, the git-native tracker in `.rohrpost/` (use the `rp` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage roles map to GitHub labels. See `docs/agents/triage-labels.md`.

### Domain docs

Multi-context layout with root `CONTEXT-MAP.md` pointing to per-game CONTEXT.md files. See `docs/agents/domain.md`.

## Rules of engagement

Canonical doc: `docs/agents/rules-of-engagement.md`. Applies to Claude Code, Codex, and Cursor.

**Default delivery:** when a task changes files and the user has not opted out, commit and push to `main`. Work on `main` in the primary checkout unless the user asks for a separate branch or worktree.

**Assets:** use the built-in imagegen tool when available; otherwise Codex image gen (`~/.claude/skills/codex-imagegen/imagegen.sh`). No API stubs or placeholder art.

**GitHub Pages:** every repo is hosted on Pages — follow `docs/agents/github-pages.md`. Implement missing paths, deploy workflow, or README as part of the task.

**Submodules:** push the linked repo's `main` first, then commit and push the updated pointer here.

## Subagent workflows

When authoring `workflow` scripts (ticket loops, implementation trains):

- Every subagent prompt that may launch a browser must end with "stop any
  chrome-agent instance you launched (`chrome-agent stop <instance>`) before
  returning" — subagents otherwise leak instances the orchestrator must clean up.
- If implementer prompts say "create NO tickets" (right, for scope), the verify
  prompt must reconcile follow-ups: scan closed tickets' comments for flagged
  follow-up work and confirm each has an actually-filed ticket. Findings
  recorded only in a close comment die there.
- Orchestrator end-of-run check: `chrome-agent status` empty, both repos' `git
  status` clean, `rp list --status open` matches expectations.

@RTK.md
