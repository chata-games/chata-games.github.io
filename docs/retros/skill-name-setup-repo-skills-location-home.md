# Retro: Verified-but-unplayable — smoke assertions that couldn't see the game, and the playtest that could

**Date**: 2026-09-01
**Session**: 01a057ed-1880-734c-b874-715c0f3f8de3
**Transcript**: /home/vfeenstr/.pi/agent/sessions/--home-vfeenstr-devel-games-chata-games--/2026-08-31T13-05-51-232Z_01a057ed-1880-734c-b874-715c0f3f8de3.jsonl
**Duration / tokens / cost**: 58,349 s (~16.2 h wall clock) / 8,555,094 total tokens (713,834 in, 92,012 out, 7,749,248 cache-read) / $0.00 (zai/glm-5.3-flash); 131 tool calls, 111 assistant messages, 0 compactions
**Extraction**: /home/vfeenstr/devel/games/chata-games/docs/retros/skill-name-setup-repo-skills-location-home.extract.json

## What happened

The session ran the `setup-repo-skills` prompt (switching the repo's tracker to Rohrpost), then verified the deployed Forest Rescue game with a CDP smoke test — which found the live game crashed on every level entry (`ReferenceError: state is not defined`), fixed that plus a second overlay bug, and worked the resulting tickets through a self-looping workflow. When the user challenged "Did you actually try to play the game?" (83e23c8e), the agent staged three concurrent agent-players in Xvfb windows, ran a debate workflow whose players found defenders never fire a single shot (19 runs, 19 defeats), and drove an implementation workflow that shipped all fixes and verified all 7 levels end to end. Deliverables: two committed e2e scripts (now the standing regression), ~20 Rohrpost tickets worked to done, both fixed builds deployed to Pages, playtest reports stored under `forest-rescue/docs/playtest/2026-08-31-agent-session/`.

## What worked

- **Event-stream forensics**: when truncated output hid the crash, the agent pulled the full `ReferenceError` from the raw CDP event log and had the app bug in 3 calls (3dcf7348, 1bbef7c8, d1bbb447).
- **Scope discipline**: pre-existing breaks found mid-fix (`npm run serve` CJS/ESM, level6-fire sim) were ticketed, not absorbed into the claim (0bc00d4a, 93fcbd59, 0cc051b7).
- **Empirical verification before fan-out**: proved 3-way render concurrency in Xvfb *before* spending the playtest workflow (b1a126c6, 517b5a0a), and independently source-verified the players' central claim before ticketing it (db01b4d6).
- **Self-correction loop**: the ticket-loop's verify agent caught the session's own flow-4 false pass and round 2 fixed it (b5b32c49).
- **Rohrpost hygiene**: claim/comment/close with evidence throughout; both e2e scripts committed as standing regressions (40443ff2, 8e8bc913).

## Friction

- **"Verified end to end" but nobody could play it** (83e23c8e, 27c2da55, aac9f42d, c5bc7c87, db01b4d6): the fix-session report claimed the game "verified end to end" with a standing regression, yet defenders never fired — every smoke flow still passed because flow 4 accepted `#endTitle ∈ {Victory, Game Over}`, i.e. an outcome assertion that passes on defeat. Only the user's challenge surfaced it. Root cause: `chrome-agent-testing` SKILL.md §2 optimizes exclusively for deterministic assertion scripts ("none reads a screenshot"), and the user's qualitative ask ("make sure the game is actually working", 41a56a45) got a regression-shaped answer; nothing in the skill flags that an outcome assertion can pass via a failure outcome, or suggests a visual pass for qualitative questions.
- **False pass from hidden-overlay static text** (b5b32c49, 6cafc228): flow 4 "battle resolves, replay visible" was claimed locally, but the hidden `#endOverlay` ships static "Game Over" text, so the script could read an outcome instantly mid-battle; the workflow's verify agent (not this session) caught it and now requires actual overlay visibility. Root cause: the skill's "sense, act, sense again" never distinguishes DOM presence from visibility, and game DOMs routinely carry pre-baked outcome text in hidden elements.
- **Frame-race assertions** (6e234791, 331fbab2, 78dc8932): the script first read mana before the first painted frame (HTML placeholder `100`), then asserted exact starting mana `150` — which mana regen had already moved to `203` by first read, failing a correctly fixed game. Root cause: the skill's "take expected values from the app's spec, seed data, or fixtures" is right for static apps but racy on a live render loop; the agent had to derive polling and relative-change assertions itself.
- **Concurrency setup derived from scratch, ~20 calls** (9fa9a519, fe0d0167, e3c005ff, 3f6182bc, 0399e382–8beea039): the user asked for "3 agents … same chrome-agent browser instance with different tabs"; the agent discovered background tabs throttle rAF (only the active tab animates, 007d4a1d/2b89f31e), that CDP `Page.setWebLifecycleState` cannot fix it (a6fbb440/2950dc52), pivoted to Xvfb with one window per agent, then fought tab-creation ambiguity twice (create attempts that "failed" had still created duplicates, e3c005ff; `--url` can't address a tab that doesn't exist yet, 3f6182bc). Root cause: the cdp-cookbook documents tab *addressing* (`--url`, index instability) but nothing about tab *creation* in multi-tab instances, throttling, or the Xvfb pattern — all pure environment knowledge that will recur on the next multi-agent playtest.
- **Workflow subagent loose ends** (7648bfdf, d4820655; f731d1f3, 7356d127): the first ticket-loop's verify agent leaked a Chrome instance the orchestrator had to hunt down; and the implementation workflow's RP-h06svz agent recorded a levels-6–7 retune finding in its close comment but filed no ticket (its guardrail said "create NO tickets"), which only a manual post-run check caught. Root cause: ad-hoc workflow prompts — teardown never mandated, and a "don't create tickets" guardrail with no reconciliation step for flagged follow-ups.
- **rohrpost wrapper not executable** (20c457b4, ce9710d9): first `claim` died with `Permission denied`; the file's git mode is `100644` (verified via `git ls-files -s`), so every fresh checkout hits this. Recovery was instant (`bash <path>`), but the skill assumes an executable wrapper and says nothing about the failure mode.

## Proposals

| # | Type | Change | Where | Evidence | Status |
|---|------|--------|-------|----------|--------|
| 1 | skill-update | Add qualitative-ask visual pass + bad-outcome caveat (text below) | `.agents/skills/chrome-agent-testing/SKILL.md` §2 and §4 | 83e23c8e, aac9f42d, c5bc7c87, db01b4d6 | done |
| 2 | skill-update | Add two cookbook sections: "Assertions on live game loops" and "Concurrent agents in one Chrome instance" (text below) | `.agents/skills/chrome-agent-testing/references/cdp-cookbook.md` | b5b32c49, 6e234791, 331fbab2, 0399e382–8beea039, 9fa9a519, fe0d0167, e3c005ff, 3f6182bc | done |
| 3 | rule-update | New `## Subagent workflows` section in AGENTS.md (text below) | `AGENTS.md` (after Rules of engagement) | 7648bfdf, d4820655, f731d1f3, 7356d127 | done — section applied; dedicated skill ticketed as RP-wmssbx |
| 4 | skill-update | Wrapper Permission-denied fallback line in rohrpost SKILL.md + restore exec bit (`git update-index --chmod=+x .agents/skills/rohrpost/scripts/rohrpost`) | `.agents/skills/rohrpost/SKILL.md` §Invocation; repo git mode | 20c457b4, ce9710d9 | done — doc line applied; local chmod applied; git-mode fix N/A: `.agents/` is untracked in this repo, so the retro's "mode 100644 in git" premise was wrong (corrected) |
| 5 | acknowledge | Stale-checkout detour (diagnosed 25 commits behind before confirming origin/main) and the sleep-1 curl race on the local server — both handled inline in-session; no durable rule warranted | — | c0a6480c, 2cff7c45, 3bc244af, 1eb42ae1 | done (acknowledged — no action warranted) |

### Proposal 1 — SKILL.md text

In §2 "Plan assertions before commands", after the paragraph ending "…propose the list and confirm before writing anything.", add:

> When the user's question is qualitative — "is it actually working/playable?" rather than "is this flow covered?" — an assertion-only plan can pass while the app is effectively broken: an outcome assertion accepts any terminal state, so a battle resolving as *Game Over* proves the loop ran, not that the game is playable. Pair the deterministic script with a one-off visual pass: screenshot at key moments and read the images; the deliverable script itself stays screenshot-free. Turn visual findings into new assertions (e.g. "defenders visibly never fire" becomes a projectile/shots-fired assertion).

In §4 "Run and iterate", append to the report paragraph:

> When an outcome assertion passed via a failure outcome (defeat, error screen, fallback content), say so explicitly — a pass that rides a bad outcome is a finding, not a green light.

### Proposal 2 — cdp-cookbook.md text

Append two sections:

````markdown
## Assertions on live game loops

Games write HUD text inside the render loop and state moves every frame, so:

- Poll past the first painted frame before reading HUD values; an immediate read
  returns the HTML placeholder (e.g. mana `100` shipped in the markup).
- Never assert exact ephemeral values (current mana, wave counters) — regen and
  passive effects move them between the action and the read. Assert relative
  changes (mana dropped after planting), thresholds, or monotonic progress
  (wave number advanced).
- Presence is not visibility. Game DOMs ship hidden overlays whose static text
  already looks like an outcome (`#endOverlay` contains "Game Over" while still
  hidden). Assert the element is actually shown
  (`!classList.contains("hidden")`, `offsetParent !== null`) before reading it
  as an outcome, and require a state transition (hidden → visible), not a
  static read.
- In a `+Network.loadingFailed` watcher, ignore `errorText: "net::ERR_ABORTED"`
  with `canceled: true` — a superseded navigation aborts its own Document load;
  that is not a broken asset.

## Concurrent agents in one Chrome instance

Background tabs are throttled: Chrome runs `requestAnimationFrame` loops only in
the most recently active tab, so a rAF-driven game freezes in every tab but one,
and `Page.setWebLifecycleState` does not fix it. To run N agents in one
instance, give each tab a real, visible window on a virtual display:

    Xvfb :99 -screen 0 3000x900x24 -nolisten tcp &
    DISPLAY=:99 chrome-agent launch -- --window-position=0,0
    # open one tab per agent, then place each on its own window position

Verify concurrency empirically before spawning agents: read a moving value
(mana, wave) in every tab twice and confirm all of them advance.

Creating tabs once more than one page target exists: a one-shot cannot address
the tab it is creating, so `--url <new-tab-key>` fails with "No target matching
URL". Address the create call at an existing tab instead
(`--target-index N Target.createTarget …`) and close the default
`chrome://newtab` first. A create "failure" may still have created the target —
list tabs (`chrome-agent status`) before retrying, or you will mint duplicates.
````

### Proposal 3 — AGENTS.md text

New section after "Rules of engagement":

```markdown
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
```

### Proposal 4 — rohrpost SKILL.md text

In `## Invocation`, after the sentence about the wrapper preserving the working directory, add:

> If the wrapper fails with `Permission denied`, its executable bit did not survive checkout (`git ls-files -s` shows mode `100644`). Run it via `bash <rohrpost-skill>/scripts/rohrpost …` and restore the bit as part of the task (`chmod +x` + `git update-index --chmod=+x <skill>/scripts/rohrpost`).

Plus the repo fix itself, applied once: `git update-index --chmod=+x .agents/skills/rohrpost/scripts/rohrpost`.

## Questions for the user

- Proposal 3 places workflow-authoring rules in AGENTS.md (cheapest durable form). If ad-hoc ticket-loop/playtest workflows become routine here, a dedicated workflow-authoring skill would carry more detail — fine to start with the AGENTS.md pointer?
  → Answered: AGENTS.md section kept; dedicated skill ticketed as RP-wmssbx.
- Should the standing Pages smoke script gain an explicit lethality assertion (shots fired / enemies killed), per Proposal 1's "turn visual findings into assertions"? It is the one regression the current scripts still cannot see.
  → Answered: ticketed as RP-gk38jw (needs-triage).
