# AGENTS.md

Stomato: an open, modular steady-state process simulator plus the engineering deliverables
(PFD, P&ID, piping, isometrics) generated from one validated model. You are one of several agents
working in parallel; an orchestrator (Claude Code) writes specs, reviews every PR and merges.
The plan and architecture are in `docs/PLAN.md`. Read it once.

**This file covers the backend (Python).** Frontend work lives in `frontend/` and follows
`frontend/AGENTS.md`. Never change both in one PR (CI rejects it).

## Commands
```
uv sync --all-groups          # install
uv run pytest -rs             # all tests (parallel). -rs lists skips
uv run pytest -n0 -k <name>   # one test, serial
uv run ruff check . --fix && uv run ruff format .
uv run mypy
uv run lint-imports           # dependency-direction contract (.importlinter)
```
CI runs exactly these. A PR merges only when CI is green and the orchestrator has reviewed it.

## How work is organised
- Every task is a spec in `specs/backend/` named in your task. Do exactly that spec.
- A spec names the **packages it may edit**. Edit existing files in those packages when the spec
  says so; create new files where it says so. Do not touch other packages.
- **Fix at the root; never stack.** If the right fix needs a file outside your packages, or a
  contract change the spec did not grant, stop and say so in the PR. Do not copy a function,
  wrap it, or add a parallel implementation to avoid editing the owner.
- **Reuse registered plugins.** If a correlation, sizer or helper already exists under
  `ngdesign.registry`, call it. Re-implementing an existing equation is a review failure.
- Plugins self-register with a decorator; discovery is automatic. Never add imports to any
  `__init__.py`.
  ```python
  from ngdesign.registry import register


  @register("unit", "compressor")
  class Compressor: ...
  ```
- Plugin kinds and their interfaces: `src/ngdesign/contracts/plugins.py`.
- HTTP routes live in `src/ngdesign/api/`. Changing a route changes `openapi.json`
  (`uv run python scripts/export_openapi.py`); CI checks it is up to date.

## Dependency direction (CI-enforced by `.importlinter`)
```
cli > api > agent > export > pipeline > flowsheets > solver > units > amine > thermo > contracts|registry|data
sizing, pid_rules, piping, render  ->  contracts|registry|data only   (never thermo/units/solver)
```
`ignore_imports` lines in `.importlinter` are known debts owned by Phase 0 specs. Delete the
lines your spec names; never add one.

## Locked (CI rejects PRs that touch these without the `contract-change` label)
`tests/golden/test_*.py`, `tests/property/`, `data/golden/`, `.github/`, `AGENTS.md`,
`pyproject.toml`, `uv.lock`.
These are the oracles and the rules. If one blocks you, stop and write why in the PR.
Need a new dependency? Stop and say so in the PR; do not add it.

Contracts (`src/ngdesign/contracts/`, `tests/contracts/`) are editable **only** when your spec
says `Contract change: yes`. Such PRs are reviewed by the orchestrator before merge.

## Conventions
- SI internally (K, Pa abs, mol/s, J/mol, W, m; piping geometry in mm). Convert only at edges.
- Reference data comes from `ngdesign.data`. Never hard-code standard tables or constants
  from memory. Never bake sample-flowsheet numbers into general code.
- Use `thermo`, `fluids`, `ht`, CoolProp where they fit. Do not re-derive what they provide.
- Pure functions; no I/O, no globals, no prints in library code.
- Type hints everywhere; mypy strict clean.
- Equation in the docstring with its source (e.g. "API 520 Pt I eq. 9", "GPSA Fig. 20-...").
- Behaviour-preserving refactors must be **byte-identical** on the golden outputs
  (`tests/e2e/test_slice.py` guards this). Say in the PR how you checked.

## Oracles (how you know you are right)
- `tests/golden/test_correlations.py`: a `correlation` plugin named like `data/golden/<name>.yaml`
  must reproduce every case.
- `tests/golden/test_thermo.py`: EOS vs CoolProp reference, flash round-trips.
- `tests/property/test_unit_balances.py`: every `unit` closes component and energy balances on its
  own `example_case()`.
- `tests/property/test_pid_rules.py`: every `pid_rule` finds violations on the bare sample P&ID,
  `check(apply(pid)) == []`, apply is idempotent, and all rules compose.
- `tests/property/test_isometric.py`: lengths, BOM, welds match the 3D model.
- `bench/baseline.json` (once P0-06 lands): flash count and wall time per benchmark flowsheet.
- Your own tests go in `tests/<layer>/test_<your_module>.py`, mirroring `src/`.

## Definition of done
1. Every acceptance criterion in the spec is true; nothing outside the spec's packages changed.
2. ruff, mypy, lint-imports, full `pytest -rs` green. Tests named in the spec PASS (not skip).
3. PR title `<spec id>: <spec title>`; body lists each acceptance criterion with a check and
   how you verified it.
4. Comment the PR URL on the GitHub issue named in your task. If blocked, comment the blocker
   there instead and stop.
5. Never merge, approve, or enable auto-merge on your own PR, and never push to `main`. The
   orchestrator reviews, approves and merges every PR (branch protection requires one approval).

## Never
- Weaken, skip, or xfail a test to get green. Loosen a tolerance.
- Duplicate an existing function instead of calling it.
- Add an `ignore_imports` line or work around the import contract.
- Leave TODOs that make an acceptance criterion untrue.
