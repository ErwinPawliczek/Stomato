# AGENTS.md

Natural gas processing design suite. One validated model produces simulation results, PFD, P&ID,
3D piping and isometric drawings. You are one of many agents working in parallel.

**This file covers the backend (Python).** Frontend work lives in `frontend/` and follows
`frontend/AGENTS.md`. Never change both in one PR (CI rejects it).

## Commands
```
uv sync --all-groups          # install
uv run pytest -rs             # all tests (parallel). -rs lists skips
uv run pytest -n0 -k <name>   # one test, serial
uv run ruff check . --fix && uv run ruff format .
uv run mypy
```
CI runs exactly these. A PR merges only when CI is green.

## How work is organised
- Every task is a spec in `specs/backend/` (or a GitHub issue). Do exactly that spec.
- HTTP routes live in `src/ngdesign/api/app.py`. Changing a route changes `openapi.json` (run
  `uv run python scripts/export_openapi.py`) and is a contract change: needs the `contract-change` label.
- **One spec = new files only.** Create the files the spec lists. Do not edit files other specs own.
- Plugins self-register with a decorator; discovery is automatic. Never add imports to any `__init__.py`.
  ```python
  from ngdesign.registry import register


  @register("unit", "compressor")
  class Compressor: ...
  ```
- Plugin kinds and their interfaces: `src/ngdesign/contracts/plugins.py`.

## Locked (CI rejects PRs that touch these)
`src/ngdesign/contracts/`, `src/ngdesign/registry.py`, `src/ngdesign/data.py`,
`src/ngdesign/flowsheets/slice.py`, `src/ngdesign/flowsheets/samples.py`, `data/`,
`tests/conftest.py`, `tests/contracts/`, `tests/golden/test_*.py`, `tests/property/`,
`.github/`, `AGENTS.md`, `pyproject.toml`.
If a locked file blocks you, stop and write the reason in the PR description. Do not work around it.
Need a new dependency? Stop and say so in the PR; do not add it.

## Conventions
- SI internally (K, Pa abs, mol/s, J/mol, W, m; piping geometry in mm). Convert only at edges.
- Reference data comes from `ngdesign.data` (pipe schedules, flange ratings, pipe classes, components).
  Never hard-code standard tables or constants from memory.
- Use `thermo`, `fluids`, `ht`, CoolProp where they fit. Do not re-derive what they provide.
- Pure functions; no I/O, no globals, no prints in library code.
- Type hints everywhere; mypy clean.
- Equation in the docstring with its source (e.g. "API 520 Pt I eq. 9", "GPSA Fig. 20-...").

## Oracles (how you know you are right)
- `tests/golden/test_correlations.py`: a `correlation` plugin named like `data/golden/<name>.yaml`
  must reproduce every case. Unimplemented = skipped; implementing it must turn skips into passes.
- `tests/golden/test_thermo.py`: Peng-Robinson vs CoolProp reference, flash round-trips.
- `tests/property/test_unit_balances.py`: every `unit` closes component and energy balances on its
  own `example_case()`.
- `tests/property/test_pid_rules.py`: every `pid_rule` finds violations on the bare sample P&ID,
  `check(apply(pid)) == []`, apply is idempotent, and all rules compose.
- `tests/property/test_isometric.py`: lengths, BOM, welds match the 3D model.
- Your own tests go in `tests/<layer>/test_<your_module>.py`, mirroring `src/`.

## Definition of done
1. Files listed in the spec exist; nothing else changed.
2. `uv run pytest -rs` green, and the tests named in the spec PASS (not skip).
3. ruff and mypy clean.
4. PR title `S-XX: <spec title>`; body lists acceptance criteria with a check each.

## Never
- Weaken, skip, or xfail a test to get green.
- Loosen a tolerance.
- Edit another spec's files.
- Leave TODOs that make an acceptance criterion untrue.
