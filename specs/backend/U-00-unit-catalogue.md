# U-00: Unit catalogue as data — YAML registry, rigour-level dispatch and refusal, V0 harness, every palette row declared

- **Phase:** Unit catalogue, round 0 (docs/unit-catalogue-plan.md §0–§5)
- **Depends on:** none
- **Packages you may edit:** `ngdesign.units` (new `catalogue.py`, `levels.py`; registration lines only in existing unit modules — see Files), `ngdesign.registry` (discover hook only), `data/unit_models/`, `data/validation_units/`, `scripts/validate_units.py`, `docs/units/`, `docs/units.md`, `.github/workflows/` (one audit step), `tests/units/`, `tests/property/test_unit_balances.py`
- **Contract change:** no (`UnitModel` protocol unchanged); the catalogue schema is new data
- **Benchmark delta expected:** none — every existing flowsheet, golden and bench count byte-identical
- **GitHub issue:** #189

## Goal
Make units data, the way `thermo.catalogue` made property packages data: one YAML row per unit in
the full 83-unit palette (docs/unit-catalogue-plan.md §2 U-A..U-H), the rigour level selected by
`params["model"]`, unimplemented levels refused with a typed error, and a harness that proves
balances on every implemented level and writes a report per unit. Round 1 family threads then only
add adapters and flip rows; they never touch the catalogue machinery.

## Files
- `data/unit_models/_schema.yaml` (validated by a test, like `data/thermo_models/_schema.yaml`): per unit `id`, `name`, `family` (`logical|flow|heat|separation|column|reactors|treating|refining`), `ports` (in/out names, required/optional), `levels: {R0|R1|R2|R3: {status: implemented_status, adapter: "module:Class", params: <JSON-schema fragment>, validation: [case ids], end_state: bool}}` where `implemented_status ∈ {validated, provisional, experimental, planned}`, `sizer`, `pid_symbol`, `references`, `notes`. A `planned` level has no adapter.
- `data/unit_models/<family>.yaml` for all eight families: every row of plan §2 (U-A..U-H, 83 units). Existing units (mixer, splitter, pump, compressor, compression train, expander, JT valve, heater/cooler, shell-and-tube, air cooler, separator 2/3-phase, TEG contactor, MDEA absorber/regenerator, column configurations, Kremser, …) get their real levels and adapters with status `provisional` unless already validated; every other level is `planned`. Count the existing registered units and list them in the PR body.
- `units/levels.py`: `UnitLevelNotImplemented(ValueError)` carrying unit id, requested level and implemented levels; `resolve_level(row, params)` — `params["model"]` absent → the unit's lowest implemented level (so every existing flowsheet keeps its current behaviour byte-identically); existing mode parameters (P1-06 `mode="shortcut"|"staged"`, column configurations) map onto levels without renaming any existing param.
- `units/catalogue.py`: load + validate YAML; `register_all(registry)` registers implemented adapters; `units_catalogue()` returns the rows for the API/agent/frontend later. Existing `@register("unit", …)` decorators stay where they are (P1-11 owns `units/column/` and `amine/` right now — do not edit those files); a test asserts the YAML implemented set equals the registered set, so the two can never drift. `registry.discover()` calls `units.catalogue.register_all` after module imports.
- `scripts/validate_units.py` (mirror `scripts/validate_properties.py`): for every implemented level — V0: mass and energy balance ≤ 1e-8 relative on `example_case()` run at that level, determinism (two solves identical), port contract, refusal of each `planned` level with `UnitLevelNotImplemented`; V1: cases from `data/validation_units/<family>/cases.yaml` (schema there; empty files now) with the same `assessed:` miss discipline as thermo; writes `docs/units/<id>.md` and the summary table `docs/units.md` (status counts per family, implemented/planned levels); `--audit` exits non-zero when a doc is stale or a `validated` level lacks V1 cases. Add `--audit` to the CI audit job.
- `tests/property/test_unit_balances.py`: extend the locked balance test to iterate the catalogue's implemented levels instead of a hard-coded list (the existing assertions and tolerances unchanged).
- `tests/units/test_catalogue.py`: schema validity; 83 rows; family counts per plan §2 (9/12/10/10/12/9/9/12); YAML↔registry agreement; level refusal message names implemented levels; default level keeps an existing flowsheet byte-identical (solve the bench flowsheets before/after).

## Acceptance criteria
- [ ] 83 rows, every existing unit present with real adapters; all others `planned`
- [ ] `validate_units.py --audit` PASS on CI; `docs/units.md` + per-unit pages generated
- [ ] bench `--check` byte-identical; goldens and e2e unchanged; openapi unchanged
- [ ] ruff, ruff format, `mypy src tests`, lint-imports, full pytest green
- [ ] No edits under `units/column/`, `amine/`, `contracts/`, `units/_physics/` (U-R owns it)

## Out of scope
Any new unit physics; API/frontend palette from the catalogue (later); reaction sets (U-R); the S0 reference data (A-01).
