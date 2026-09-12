# Architecture

## Product shape

Media Reach Planner is a static, client-side web application. There is no application backend, database, authentication layer, or server-side media-plan processing.

Production shell: `index.html`.

Current product surfaces:

- **Охваты и KPI** — legacy production planner, Web core 0.52.
- **Reach Engine v1.6** — isolated methodology/calculation console.
- **Флоучарт** — annual/multi-plan flowchart plus 1:1 PowerPoint export.
- **Сплиты** — plan/fact/delta split analysis.
- **Подробнее** — explanatory/detail surface.

## Runtime

The browser loads:

- Pyodide `v314.0.6` from CDN;
- Reach v1.6 static JS/CSS/Python files from this repository;
- `html2canvas 1.4.1` and `PptxGenJS 3.12.0` for flowchart PPTX export.

Media-plan files are parsed locally in the browser. Do not introduce remote file upload as an incidental implementation detail.

## Two Python cores

### 1. Legacy Web 0.52 core

Canonical source files:

- `.debug_sources/engine.py`
- `.debug_sources/web_api.py`
- `.debug_sources/xlsx_reader.py`
- `.debug_sources/splits.py`

Their production runtime copies are gzip+base64 embedded inside `index.html` as `window.MRP_ASSETS`.

**Rule:** edit the files in `.debug_sources/`, never the encoded payload by hand. Then rebuild with:

```bash
make rebuild-embedded
make verify-embedded
```

The GitHub workflow `.github/workflows/rebuild-embedded.yml` also rebuilds the embedded payload after canonical legacy sources land on `main`, but local synchronization before a PR is preferred because it makes the PR self-contained and testable.

### 2. Reach Engine v1.6

Canonical source files:

- `reach_v16_math.py` — mathematical primitives and model constants.
- `reach_v16.py` — plan normalization, model orchestration, diagnostics and hierarchy output.
- `reach_v16.js` — Pyodide bridge, browser state, rendering and user interactions.
- `reach_v16.css` — isolated Reach v1.6 presentation.
- Reach v1.6 markup in `index.html` — only the section beginning with `<section id="tab-reach16"`.

Reach v1.6 Python is loaded as a normal static asset at runtime; it is **not** part of `window.MRP_ASSETS`.

## Important boundary: legacy vs Reach v1.6

A Reach-only change must not mutate unrelated legacy production HTML/JS/CSS. The repository has a guard that removes the isolated Reach section and normalizes Reach asset cache versions, then compares the remainder of `index.html` with `origin/main`.

Run:

```bash
make guard-reach-surface
```

Do not use this guard for intentional legacy/flowchart/splits changes; those changes must instead be reviewed and tested as production-shell changes.

## Testing layers

### Legacy core

Tests under `.debug_sources/` cover engine, web API, splits and XLSX reader behavior.

### Reach Engine v1.6

- `test_reach_v16_math.py` — mathematical invariants.
- `test_reach_v16.py` — orchestration, contracts and UX/source assertions.
- `test_reach_v16_lab_fixture.py` — LAB/browser-like integration fixture.
- `test_reach_v16_persil_battle.py` — cross-plan planner benchmarks.
- `test_reach_v16_template_battle.py` — parser/template robustness.
- `test_reach_v16_final_ux.py` — final UI contract checks.

Battle fixtures are intentionally used to prevent tuning a formula to a single media plan.

## Deployment

### GitHub Pages

`.github/workflows/pages.yml` deploys every push to `main`.

Production URL:

`https://lxkochetov94.github.io/media-reach-split-planner-web/`

### Netlify

`netlify.toml` publishes the repository root and defines security/cache headers. Pull requests currently receive Netlify deploy previews through the connected project.

## Generated vs canonical data

| Area | Canonical | Generated / derived |
|---|---|---|
| Legacy Python | `.debug_sources/*.py` | `window.MRP_ASSETS` inside `index.html` |
| Reach v1.6 | `reach_v16*.py/js/css` | rendered browser UI |
| Media-plan results | uploaded XLSX/XLSM + model inputs | runtime results only |
| Flowchart PPTX | current rendered flowchart | downloaded `.pptx`, never committed |

## Architectural constraints

- Static-first and browser-local are product properties, not accidental implementation details.
- Reach must obey set-theory bounds and frequency monotonicity; invalid results should fail, not be silently capped.
- Cross-platform Reach is a planning model when user-level deduplicated data is unavailable.
- Parser ambiguity must remain diagnosable. Do not silently invent media-plan semantics when a template is ambiguous.
