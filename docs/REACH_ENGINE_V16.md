# Reach Engine v1.6

This document is the methodology/engineering contract for the isolated Reach Engine v1.6 surface.

## Product intent

Reach Engine v1.6 has two calculation modes with different purposes.

### AUTO

AUTO is the fast, repeatable mass-planning path. It must be usable across tens of media plans without manual setup.

AUTO:

- calculates independently from the finished Reach value that may already exist in the uploaded plan;
- uses Technical Reach / Impressions / source Frequency plus stable model defaults;
- exposes **K** as the user sensitivity control, default `2.44`;
- does not expose B/D/L as active inputs;
- aggregates fragments of the same platform inside a Flight before applying the fast AUTO people conversion;
- does **not** apply the Detailed Web temporal browser/device deduplication to those fragments;
- builds a simple planning frequency curve and then the higher-level audience unions.

If source Reach is present in a media plan, it is a QA benchmark only. It may be displayed as a delta but must not be fed back into the AUTO result.

### Detailed Web

Detailed Web exists to model nuances that AUTO intentionally ignores.

It may use:

- B — browser IDs per device;
- D — devices per person;
- L — browser-ID stability window;
- web/device Universe assumptions;
- environment/browser-family assumptions;
- temporal effects and deeper ID-path logic.

Detailed Web is not required to stay close to AUTO. Depending on the assumptions, Detailed Reach may be higher or lower.

For blank B/D fields, the UI should clearly communicate that the engine uses AUTO values for the target audience and that the user can enter an override.

## Current AUTO defaults

Canonical constants are in `reach_v16_math.py`. Do not duplicate them in docs/tests as independent business logic.

Important defaults currently include:

- `K_DEFAULT = 2.44`;
- a fixed AUTO people-conversion baseline calibrated across multiple project fixtures;
- a fixed planner reachability profile for the frequency curve.

These defaults must not be retuned against a single uploaded plan.

## Frequency semantics

User-facing frequency notation is:

`@1+`, `@2+`, `@3+`, `@4+`, `@5+`, `@6+`.

Requirements:

- cumulative Reach is monotonic: `@1+ >= @2+ >= ... >= @6+`;
- Reach cannot exceed the relevant Universe;
- exact buckets must reconcile to cumulative Reach;
- average frequency is displayed with one decimal in business UI;
- the Effective Reach chart uses a fixed 0–100% Y axis;
- selected KPI frequency uses the common beige highlight.

## Audience-union semantics

At Channel/Flight/Line/Brand levels, Reach is an audience union, not arithmetic summation.

Invariants:

- union >= largest child Reach;
- union <= Universe;
- impossible input/output should raise a validation/calculation error rather than silently cap the result;
- order should not change the result where the model is defined as order-invariant.

## Source Reach

Source Reach fields found in XLSX/XLSM are useful for:

- QA;
- regression benchmarking;
- detecting parser/model drift;
- comparing the planner model with existing planning conventions.

They are **not** allowed to become a hidden target that modifies the current plan's AUTO result.

If a source curve is invalid, conflicting or non-monotonic, ignore it for QA and surface diagnostics rather than repairing it silently.

## Structure of real media plans

A recurring failure mode is testing a simplified structure that does not match how the XLSX parser groups rows.

For LAB-like plans, one logical Flight can contain monthly fragments of the same platform. Browser-like integration tests must preserve this structure when the bug depends on grouping.

AUTO multi-fragment platform path:

1. sum/resolve Technical Reach at platform/Flight scope;
2. aggregate Impressions;
3. derive aggregate technical Frequency;
4. apply AUTO people conversion once;
5. build AUTO frequency curve;
6. union platforms/channels upward.

Detailed Web is allowed to keep the temporal fragment path because temporal ID stability is part of its purpose.

## UI contract

The main business view should be understandable without internal model codes.

Keep:

- status / warnings;
- Reach by frequency in % and people;
- key results;
- Effective Reach chart;
- exact contact distribution;
- Channel → Platform drill-down hierarchy;
- separate technical diagnostics below/behind the business view.

Avoid:

- raw validation codes in the primary UI;
- redundant words such as `человек` when a table column already says `Люди`;
- different typography for the same total KPI only because that KPI is selected;
- showing B/D/L as editable AUTO controls.

## Regression strategy

A methodology change should normally touch more than one test layer:

1. mathematical unit invariant in `test_reach_v16_math.py` or `test_reach_v16.py`;
2. LAB/browser-like fixture when grouping/runtime path matters;
3. Persil/template battle fixture when a global heuristic/default changes;
4. UX/source contract test if visible behavior changes.

Before accepting a new global default, inspect multiple normal benchmark plans and call out outliers instead of forcing the default to fit every source convention.

## Production isolation

Reach v1.6 is intentionally isolated from legacy Web 0.52. For Reach-only tasks run:

```bash
git fetch origin main
make guard-reach-surface
```

A failure means `index.html` changed outside the allowed isolated Reach section/cache references and must be reviewed explicitly.
