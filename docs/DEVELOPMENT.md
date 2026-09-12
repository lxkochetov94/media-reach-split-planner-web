# Development

## Requirements

Local checks require only:

- Python 3.11+ recommended;
- Node.js (used for JavaScript syntax checking);
- GNU Make for the convenience commands below;
- Git.

The Python test suites currently use the standard library only. There is no pip/npm installation step and no package lockfile.

The browser application needs network access to load CDN runtime dependencies (Pyodide, html2canvas and PptxGenJS).

## Quick start

Serve the repository root instead of opening `index.html` through `file://`:

```bash
make serve
```

Then open:

`http://localhost:8000/`

## One-command verification

```bash
make check
```

This is the default verification command for Codex and human contributors. It checks:

1. Python syntax for canonical legacy and Reach v1.6 files;
2. JavaScript syntax for `reach_v16.js`;
3. legacy Web 0.52 unit tests;
4. Reach Engine v1.6 unit/integration/battle tests;
5. embedded legacy source parity;
6. lightweight documentation/repository contract checks.

## Focused commands

```bash
make check-legacy
make check-reach
make verify-embedded
make docs-check
```

Reach-only work should additionally run:

```bash
make guard-reach-surface
```

The guard requires an `origin/main` ref. If the local clone has not fetched it recently:

```bash
git fetch origin main
make guard-reach-surface
```

## Editing the legacy Web 0.52 core

1. Edit canonical files in `.debug_sources/`.
2. Run:

```bash
make rebuild-embedded
make verify-embedded
make check
```

3. Review both the canonical Python diff and the generated `index.html` payload change.

Never manually edit the compressed/base64 `window.MRP_ASSETS` values.

## Editing Reach Engine v1.6

Read `docs/REACH_ENGINE_V16.md` first.

Typical files:

- math/model change: `reach_v16_math.py`, `reach_v16.py`, tests;
- UI logic: `reach_v16.js`;
- visual-only: `reach_v16.css`;
- Reach markup: isolated `tab-reach16` section in `index.html`.

After changing a static Reach asset, bump the `?v=` cache suffixes in `index.html` consistently when browser cache invalidation is required. `reach_v16.js` may also carry versioned Python module fetch URLs; keep them consistent when those modules changed.

Run:

```bash
make check-reach
git fetch origin main
make guard-reach-surface
```

For a final PR, run `make check` as well.

## Editing the production shell / flowchart / splits

These are intentional `index.html` changes outside the isolated Reach v1.6 section. The Reach-surface guard is not applicable to such a task.

Because `index.html` contains both human-readable production code and generated embedded Python assets, keep changes narrowly scoped and review the diff carefully.

Flowchart PowerPoint export currently relies on `html2canvas` and `PptxGenJS` loaded from CDN and exports the rendered flowchart as a single 16:9 slide image.

## Tests and fixtures

Do not "fix" a failing model test by weakening its tolerance without explaining why the methodology changed.

When a change affects Reach calculations:

- add/adjust a deterministic unit test for the mathematical rule;
- add a browser-like or battle fixture when the bug depends on media-plan structure;
- check more than one plan when changing a global default or heuristic;
- preserve monotonicity `@1+ >= @2+ >= ... >= @6+`;
- preserve set-theory bounds and Universe caps.

## PR checklist

Before handing a PR to review:

```bash
make check
git status --short
```

For Reach-only PRs:

```bash
git fetch origin main
make guard-reach-surface
```

For legacy core PRs:

```bash
make rebuild-embedded
make verify-embedded
```

The PR description should state:

- user-visible behavior changed;
- methodology changed, if any;
- files/surfaces intentionally touched;
- tests/fixtures run;
- deployment/cache implications.
