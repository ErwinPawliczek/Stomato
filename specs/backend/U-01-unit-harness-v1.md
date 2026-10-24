# U-01: Unit harness V1 cases, reactive V0 balances, per-row thermo

- **Phase:** Unit catalogue, between round 0 and round 1 (docs/unit-catalogue-plan.md §4)
- **Depends on:** U-00 (#197), U-R (#199)
- **Packages you may edit:** `scripts/validate_units.py`, `ngdesign.units.catalogue` (row fields only), `data/unit_models/_schema.yaml`, `tests/units/`
- **Contract change:** no (`UnitModel` unchanged); two optional catalogue row fields
- **Benchmark delta expected:** none; generated `docs/units*` byte-identical
- **GitHub issue:** none (orchestrator-built ahead of the round-1 dispatch)

## Goal
Round 1 adds about 50 R0 units in nine parallel threads. Each needs cited V1 comparisons and reactors need
mass/element balances. Before this spec the V1 runner only re-solved `example_case()` and compared nothing.
The harness owns these rules once, so no family thread edits it.

## Method
- V1 case schema (module docstring of `scripts/validate_units.py`): `id`, `unit`, `level`, `source`
  (mandatory citation), `thermo`, `feeds` (replace the example feeds), `params` (laid over the example
  params), and `expected` entries of `{quantity, value, tol_rel | tol_abs}`. A case may also carry `assessed`.
- Quantities: `duty_W`, `power_W`, `info.<key>`, `outlet.<port>.<field>`, and
  `outlet.<port>.composition.<cid>`.
- Findings fail the run, exactly like V0 failures. A finding is any of:
  - an unassessed miss;
  - a case with no source or no expected values;
  - a level `validation` id with no case;
  - a `validated` level whose case fails.
- Row field `balance: molar | mass_elements`. On `mass_elements` rows, V0 checks total mass and the atom
  flow of each element, and energy uses `kinetics.enthalpy_with_formation`.
- Row field `example_thermo`: the package the row's example and V1 cases solve on. The default is `pr`.
- Per-unit docs pages gain a "V1 worked cases" table when the unit has cases.

## Acceptance criteria
- [x] `validate_units.py --audit` on the current catalogue: V0 139/139, V1 0/0, docs byte-identical
- [x] `tests/units/test_validate_units_v1.py`: pass, unassessed miss, assessed miss, missing source and
  expected, bad quantity path, feeds override, dangling validation id, mass/element balance
- [x] ruff, ruff format, `mypy src tests`, lint-imports green
