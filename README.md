# Media Reach Planner Web

Static client-side media-planning application for Reach/KPI calculation, Reach Engine v1.6 methodology checks, annual flowcharts and split analysis.

## Production

- Legacy production core: **Web 0.52**
- Reach Engine: **v1.6**
- Current Reach static asset version: **1.6.21**
- Production: https://lxkochetov94.github.io/media-reach-split-planner-web/
- Architecture: static/client-side, no application backend, database or authentication
- Uploaded `.xlsx` / `.xlsm` media plans are processed locally in the browser

## Product surfaces

- **Охваты и KPI** — stable Web 0.52 planner.
- **Reach Engine v1.6** — isolated AUTO / Detailed Web Reach methodology and diagnostics.
- **Флоучарт** — annual and multi-plan flowchart with 1:1 PowerPoint export.
- **Сплиты** — plan/fact/delta analysis.
- **Подробнее** — supporting details and diagnostics.

## Start developing

Codex and human contributors should read `AGENTS.md` first.

Serve the repository root:

```bash
make serve
```

Open `http://localhost:8000/`.

Run the complete local verification suite:

```bash
make check
```

No pip/npm install step is currently required for the Python/JS checks. The full browser UI needs network access for CDN runtime libraries including Pyodide and the PowerPoint export dependencies.

## Repository map

- `AGENTS.md` — compact instructions/map for Codex and other coding agents.
- `ARCHITECTURE.md` — runtime architecture and source-of-truth boundaries.
- `docs/CURRENT_STATE.md` — current production behavior, versions and known risks.
- `docs/DEVELOPMENT.md` — exact local commands, test workflow and PR checklist.
- `docs/REACH_ENGINE_V16.md` — methodology contract for AUTO vs Detailed Web.
- `index.html` — production shell and embedded legacy Web 0.52 runtime.
- `.debug_sources/` — **canonical** legacy Python sources despite the historical directory name.
- `reach_v16_math.py` / `reach_v16.py` — Reach Engine model/math.
- `reach_v16.js` / `reach_v16.css` — Reach Engine browser bridge/UI.
- `test_reach_v16*.py` — Reach model, integration, battle and UX regression suites.
- `scripts/` — deterministic embedded-core rebuild/verification and repository guards.

## Important source-of-truth rule

The legacy Python core is embedded into `index.html` as compressed `window.MRP_ASSETS`, but the canonical files are `.debug_sources/{engine,web_api,xlsx_reader,splits}.py`.

After changing those sources:

```bash
make rebuild-embedded
make verify-embedded
make check
```

Never hand-edit the encoded payload.

## Reach Engine v1.6 guardrail

Reach v1.6 is intentionally isolated from legacy Web 0.52. For a Reach-only task:

```bash
git fetch origin main
make guard-reach-surface
```

AUTO must calculate independently from finished source Reach in the media plan. Source Reach is QA/reference only. Detailed Web is the deeper B/D/L path and may legitimately return higher or lower Reach than AUTO.

## Deployment

- `.github/workflows/pages.yml` deploys `main` to GitHub Pages.
- Netlify is connected for deploy previews and publishes the repository root.
- `.github/workflows/rebuild-embedded.yml` keeps embedded legacy Python synchronized after canonical legacy-source changes.
- Repository checks are defined in the Makefile and mirrored in GitHub Actions.

## Historical audit

`AUDIT_0.52.md` records the Web 0.52 mathematical/technical audit. For current versions, commands and methodology, prefer the documents linked above and current `main`.
