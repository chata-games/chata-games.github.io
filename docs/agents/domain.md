# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`CONTEXT-MAP.md`** at the repo root — it points to one `CONTEXT.md` per game context.
- **`CONTEXT.md`** at the repo root for org-wide terminology and architecture.
- **Per-game `CONTEXT.md`** in each game directory (`trolluv-sklep/CONTEXT.md`, `unikovka/CONTEXT.md`, etc.) for game-specific domain language.
- **`docs/adr/`** — read org-wide ADRs. In individual game repos, also check `<game>/docs/adr/` for game-scoped decisions.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

## File structure

Multi-context repo (this one):

```
/
├── CONTEXT-MAP.md                     ← org-wide map to game contexts
├── CONTEXT.md                         ← org-wide terminology
├── docs/adr/                          ← org-wide architectural decisions
├── trolluv-sklep/
│   ├── CONTEXT.md                     ← game-specific domain language
│   └── docs/adr/                      ← game-specific decisions
├── unikovka/
│   ├── CONTEXT.md
│   └── docs/adr/
├── daligame/
│   ├── CONTEXT.md
│   └── docs/adr/
├── forest-rescue/
│   ├── CONTEXT.md
│   └── docs/adr/
├── grunts-way-home/
│   ├── CONTEXT.md
│   └── docs/adr/
└── tvojekariera/
    ├── CONTEXT.md
    └── docs/adr/
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (event-sourced orders) — but worth reopening because…_
