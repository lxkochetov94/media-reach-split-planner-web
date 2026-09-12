# AGENTS.md

This repository is the production Media Reach Planner. Treat the repository itself as the source of truth.

## Start here

Before changing code, read:

1. `README.md` — product and quick start.
2. `ARCHITECTURE.md` — component boundaries and sources of truth.
3. `docs/CURRENT_STATE.md` — current production behavior and versions.
4. `docs/DEVELOPMENT.md` — exact local checks and deployment workflow.
5. `docs/REACH_ENGINE_V16.md` — Reach Engine methodology/UX constraints when touching v1.6.

## Non-negotiable boundaries

- `index.html` is the production shell and contains the legacy Web 0.52 UI plus embedded Python assets.
- Canonical legacy Python sources are in `.debug_sources/`. Do **not** hand-edit the compressed `window.MRP_ASSETS` payload in `index.html`.
- After changing `.debug_sources/{engine,web_api,xlsx_reader,splits}.py`, run `make rebuild-embedded` and `make verify-embedded` before finishing.
- Reach Engine v1.6 is isolated in `reach_v16.py`, `reach_v16_math.py`, `reach_v16.js`, `reach_v16.css`, its tests, and the `<section id="tab-reach16">` surface in `index.html`.
- Reach v1.6 work must not accidentally modify the legacy Web 0.52 surface. Run `make guard-reach-surface` when the task is Reach-only.
- Do not silently change methodology to make one fixture match. Source Reach from a media plan is QA/reference data, not an input that is allowed to force AUTO output.
- AUTO and Detailed Web are intentionally different paths. See `docs/REACH_ENGINE_V16.md` before changing Level 2/3 math.
- Do not weaken validations, invariants, or tests to make a change pass.

## Required checks

For any code change, run:

```bash
make check
```

For legacy embedded-core changes, additionally run:

```bash
make rebuild-embedded
make verify-embedded
make check
```

For Reach-only changes, additionally run:

```bash
make guard-reach-surface
```

For documentation-only changes, at minimum run:

```bash
make docs-check
```

## Development conventions

- Python: standard library only unless a task explicitly requires a new dependency.
- JavaScript: browser-native ES code; no bundler/build step currently exists.
- Keep the app static and client-side unless the task explicitly changes architecture.
- Uploaded media-plan data must remain local to the browser; do not add server upload/telemetry without an explicit product decision.
- Prefer small named helpers over more inline logic in `index.html`.
- New behavior needs a regression test. For parser/math changes, use a realistic fixture or battle test when possible.
- Keep user-facing copy in Russian unless the surrounding UI is deliberately technical/English.
- Do not expose internal error codes in the main business UI; diagnostics may contain them.

## Definition of done

A task is done only when:

- behavior matches the user request;
- canonical source and generated/embedded copies are synchronized where applicable;
- relevant regression tests pass;
- `make check` is green;
- production/deployment constraints are preserved;
- docs are updated if architecture, commands, versions, or methodology changed;
- the working tree is clean and changes are committed by the environment/workflow handling the task.
