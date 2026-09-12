# Current state

Last reviewed for the Codex handoff: 2026-09-12.

## Production

- Product: **Media Reach Planner Web**.
- Legacy production core shown in UI: **0.52**.
- Reach Engine: **v1.6**, current static asset cache version **1.6.21**.
- Primary deployment: GitHub Pages.
- Production URL: `https://lxkochetov94.github.io/media-reach-split-planner-web/`.
- Netlify is connected for deploy previews and can also publish the repository root.
- Application architecture: static/client-side; media plans are processed in the browser.

## Current surfaces

### Охваты и KPI

Stable legacy Web 0.52 planner. This is still a production surface and must not be accidentally changed by Reach v1.6 work.

### Reach Engine v1.6

Current UX/model contract:

- frequencies shown as `@1+`…`@6+`;
- Universe, impressions, Reach in people/% and average frequency are surfaced;
- AUTO is the fast mass-planning path;
- Detailed Web exposes B/D/L nuances and may produce a result above or below AUTO;
- K defaults to `2.44` and is the user sensitivity control in AUTO;
- source Reach from the uploaded media plan is QA/reference only and must not force model output;
- exact-contact distribution and Effective Reach chart are shown together;
- hierarchy output supports Channel → Platform drill-down plus Flight/Line/Brand totals;
- selected KPI frequency uses the shared beige UI treatment;
- the chart uses a 0–100% Y axis;
- browser-like LAB and Persil battle fixtures protect against single-plan overfitting.

See `docs/REACH_ENGINE_V16.md` before changing the model.

### Флоучарт

- single/multi-plan annual flowchart;
- uses the selected Line/Flights from the planner state;
- supports **PPTX export** of the current rendered flowchart;
- export uses `html2canvas` + `PptxGenJS` and produces a 16:9 slide with a 1:1 visual snapshot.

### Сплиты

Legacy split analysis remains sourced from `.debug_sources/splits.py` through the embedded Web 0.52 core.

## CI / deployment state

Existing workflows:

- `.github/workflows/pages.yml` — deploy repository root to GitHub Pages on `main`.
- `.github/workflows/rebuild-embedded.yml` — validate canonical legacy Python, rebuild `window.MRP_ASSETS`, verify byte parity and push generated `index.html` when required.
- `.github/workflows/test-reach-v16.yml` — Reach v1.6 syntax/regression tests plus protection against accidental changes outside the isolated Reach surface.

The Codex handoff adds a root `Makefile` so the same checks can be run locally before a PR.

## Known technical debt / risks

These are not reasons to rewrite the project during an unrelated task.

1. **`index.html` is large and monolithic.** It contains the production shell, legacy JS/CSS and embedded Python payload. Refactoring it should be a deliberate migration with regression coverage, not opportunistic cleanup.
2. **Legacy canonical sources live under `.debug_sources/`.** The name is historical and misleading, but changing the path would touch workflows/runtime conventions. Treat the directory as production source until a planned migration.
3. **Browser runtime depends on public CDNs.** Local Python tests do not, but the full browser UI requires network access to Pyodide and PPTX-export libraries.
4. **There is no browser E2E suite.** Current confidence comes from deterministic Python tests, JS syntax checks, fixture/battle tests and deploy previews. Visual changes still need manual preview review.
5. **`main` is not protected at repository level.** Quality depends on PR discipline and CI rather than GitHub branch-protection enforcement.
6. **Planning Reach remains a model.** Without user-level deduplicated data, cross-platform Reach is not ground truth. Defaults should be calibrated across multiple historical plans, not one file.

## Do not resurrect stale assumptions

Older documents/PRs may mention:

- Web 0.42/0.51 as current;
- source-Reach calibration as a calculation input;
- AUTO temporal browser/device deduplication for monthly fragments;
- standalone contribution blocks in Reach v1.6.

Those are superseded by current `main` and the docs in this handoff.
