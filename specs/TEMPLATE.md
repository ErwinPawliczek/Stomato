# <ID>: <title>

- **Phase:** 0 | 1 | 2 | ...   (docs/PLAN.md)
- **Depends on:** <IDs merged to main> or none
- **Packages you may edit:** `ngdesign.<pkg>`, `tests/<layer>/`
- **Contract change:** no | yes (which models, why)
- **Benchmark delta expected:** none | <case>: flashes −X %, wall ±Y %
- **GitHub issue:** #<n>  (comment your PR URL here when open)

## Goal
One or two sentences: what this adds or fixes and why it matters structurally.

## Files
- Create: `...`
- Edit: `...`
- Delete: `...`

## Method
Equations / rules with sources. Units. Edge cases. For refactors: what must stay byte-identical.

## Acceptance criteria
- [ ] ...
- [ ] Tests named here PASS (not skip): `<path::name>`
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green
- [ ] Nothing outside the listed packages changed

## Out of scope
What not to do.
