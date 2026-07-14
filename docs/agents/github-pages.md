# GitHub Pages

Every repository in the **chata-games** org is hosted on **GitHub Pages**. Agents must know this, follow the conventions below, and **implement anything missing** (paths, workflow, README) as part of the task — not leave it for later.

## URLs

| Repo kind | Live URL |
|-----------|----------|
| Game repo `chata-games/<name>` | `https://chata-games.github.io/<name>/` |
| Org index `chata-games.github.io` | `https://chata-games.github.io/` (games linked as `<name>/` subpaths via submodules) |

Games are served under a **subpath**, never at the domain root. All shipped asset and fetch URLs must work from that subpath.

## Path conventions

- **Never** use root-absolute paths in shipped code (`/assets/…`, `fetch("/levels/…")`).
- **Static sites:** relative paths only (`assets/…`, `js/…`, `./styles.css`).
- **Vite / bundlers:** set `base: './'` and resolve assets with `import.meta.env.BASE_URL` (see `trolluv-sklep/vite.config.ts` and `trolluv-sklep/src/game/assets.ts`).
- **HTML:** `<script src="…">`, `<link href="…">`, and CSS `url(…)` must be relative or BASE_URL-aware.
- Add **`.nojekyll`** at the site root if the published tree contains paths GitHub would ignore (e.g. underscore-prefixed dirs).

## Deployment workflow

Each publishable repo needs **`.github/workflows/deploy.yml`**. Reference implementation: `trolluv-sklep/.github/workflows/deploy.yml`.

**Built site** (npm/vite/etc.):

1. `npm ci` → `npm run build`
2. `actions/upload-pages-artifact` with `path: dist` (or the project's output dir)
3. `actions/deploy-pages@v4`

**Static site** (no build step):

1. `actions/upload-pages-artifact` with the site root (exclude dev-only dirs in the workflow if needed: `tools/`, `tests/`, `.github/`, etc.)
2. `actions/deploy-pages@v4`

Workflow requirements for all repos:

- Trigger on push to `main` (+ optional `workflow_dispatch`)
- Permissions: `contents: read`, `pages: write`, `id-token: write`
- Concurrency group `pages`, `cancel-in-progress: true`
- Deploy job uses environment `github-pages`

Document in the repo README that **Settings → Pages → Source: GitHub Actions** must be enabled once (agents cannot set this via git).

## Agent checklist

When touching a repo, verify and fix if needed:

1. **Paths** — no root-absolute URLs in code shipped to Pages.
2. **Workflow** — `.github/workflows/deploy.yml` exists and matches the build model (built vs static).
3. **README** — short "GitHub Pages" section with live URL and one-time Settings note.
4. **New game** — also add a card to `chata-games.github.io` `index.html` and register the submodule on the org repo.

If the task introduces assets, routes, or a build step, confirm the deploy workflow still publishes the correct output directory.
