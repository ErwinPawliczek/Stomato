# S-01: Peng-Robinson thermo package

- **Wave:** 0
- **Depends on:** none
- **Plugin:** kind `thermo`, name `pr`

## Goal
Provide PT, PH, PS flashes for the 14 components, returning full `StreamState` with phases. Every unit op depends on this, so it is the top priority.

## Files (create only these)
- `src/ngdesign/thermo/pr.py`
- `tests/thermo/test_pr.py`

## Method
Wrap the `thermo` library (Caleb Bell): `ChemicalConstantsPackage`, `PRMIX` (kijs from
`thermo.interaction_parameters.IPDB` 'ChemSep PR' where available, else 0), `CEOSGas`/`CEOSLiquid`, and
`FlashVLN` with two liquid phases so free water forms an aqueous phase.
- Component ids map to names/CAS via `ngdesign.data.components()` (C6+ = n-hexane).
- Drop components with zero fraction before calling thermo; map back afterwards.
- Phase classification: vapor = gas phase; a liquid with water mole fraction > 0.5 = AQUEOUS, else HC_LIQUID.
- Fill per phase: mole_fraction, composition, density (kg/m3), viscosity (Pa.s, from thermo if available,
  else None), z_factor (vapor), molecular_weight.
- StreamState.vapor_fraction = vapor phase mole fraction (0 if none).
- Enthalpy/entropy on a consistent reference (thermo's ideal-gas reference is fine) in J/mol, J/(mol K).
- Cache the constructed flasher per sorted component set (functools.lru_cache).

## Acceptance criteria
- [ ] `tests/golden/test_thermo.py` ALL PASS (pure-gas density vs CoolProp within 5%, PH and PS round-trips within 0.05 K, two-phase material balance, free water phase, slice inlet vapor + HC liquid + aqueous)
- [ ] Own tests: single-component; flash of TEG/H2O lean glycol at 325 K / 7.1 MPa is all liquid
- [ ] Use ChemSep PR kijs: without them the slice inlet may not split into three phases (`test_slice_inlet_three_phase`)
- [ ] Flash of slice inlet takes < 1 s
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Native PR implementation (that is S-40). Electrolytes, amine VLE.
