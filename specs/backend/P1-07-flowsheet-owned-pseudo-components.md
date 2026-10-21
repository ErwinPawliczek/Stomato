# P1-07: Pseudo-component definitions owned by the Flowsheet

- **Phase:** 1 (follow-up from the P1-02 review)
- **Depends on:** P1-02
- **Packages you may edit:** `ngdesign.contracts` (`components.py`, `flowsheet.py`), `ngdesign.data` (`register_pseudo` becomes an adapter), `ngdesign.solver` (resolution at solve entry), `ngdesign.thermo` (only where records are resolved), `tests/contracts/`, `tests/data/`, `tests/solver/`, `tests/thermo/`, `openapi.json` + `schema.d.ts` (regenerated)
- **Contract change:** yes — `Flowsheet.components` entries may carry a pseudo definition
- **Benchmark delta expected:** none

## Goal
P1-02 registers pseudo-components in a process-global dict (`ngdesign.data._PSEUDOS`), so two
flowsheets in one API process cannot both define `C7+` differently, and a saved project does not carry
its own pseudo definitions. The flowsheet is the unit of ownership: its slate must be self-describing.

## Files
- Edit `contracts/components.py`: `PseudoDefinition(Model)`: `id`, `name`, `Tb` (K), `sg` (water = 1),
  optional overrides `mw`, `Tc`, `Pc`, `omega` with a `provenance` note each. `ComponentRef = str |
  PseudoDefinition`.
- Edit `contracts/flowsheet.py`: `Flowsheet.components: list[ComponentRef]`; a validator keeps the
  derived-from-feeds default and rejects a pseudo id that shadows a curated id; `Flowsheet.slate_ids()
  -> list[str]` returns the ids in order.
- Edit `ngdesign.data`: `component_record(key, *, pseudos: Mapping[str, PseudoDefinition] | None =
  None)`; `register_pseudo` stays as a thin adapter that writes into a module-level default mapping
  **used only when no flowsheet context is given** (tests, scripts) and is documented as such.
- Edit `solver/sequential_modular.py`: `resolve_set(fs.components)` passes the flowsheet's pseudo
  definitions; the thermo package gets its records through a `ComponentSet` built once per solve (the
  `_flasher_for` cache key gains the pseudo definitions' hash so two flowsheets never share a flasher
  built from different definitions).
- Tests: two flowsheets with different `C7+` definitions solve in one process and give different
  bubble pressures; a project JSON round-trips its pseudo definitions; `openapi.json` carries the union
  type; existing P1-02 tests pass with `register_pseudo` unchanged.

## Acceptance criteria
- [ ] All tests above PASS; slice byte-identical; `bench --check` unchanged
- [ ] `openapi.json`/`schema.d.ts` regenerated; `check:api` + `typecheck` green
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green; nothing outside the listed packages changed
