# T-04: Helmholtz / reference adapter — IAPWS steam, CoolProp fluids, GERG-2008, BWRS

- **Phase:** Thermo catalogue, wave 1
- **Depends on:** T-01
- **Packages you may edit:** `ngdesign.thermo` (new `helmholtz.py`), `data/thermo_models/helmholtz.yaml`, `data/validation/helmholtz/`, `tests/thermo/`, `pyproject.toml` + `uv.lock` **only to add the optional extra `coolprop = ["CoolProp>=6.6"]`** (the orchestrator applies the `contract-change` label)
- **Contract change:** no
- **Benchmark delta expected:** none

## Goal
Family D: reference-quality equations for water/steam and for the fluids where a multi-parameter
Helmholtz EOS exists, plus GERG-2008 for natural-gas mixtures. The `thermo` library has
`IAPWS95Gas`/`IAPWS95Liquid` and `CoolPropPhase` wrappers; BWRS is in-house (Starling 1973).

## Files
- `thermo/helmholtz.py`: `IAPWSPackage` (pure water only; refuses other components by name),
  `CoolPropPackage(backend="HEOS")` for pure fluids and binary/multicomponent mixtures where
  CoolProp carries mixture parameters, `GERGPackage` (CoolProp backend "HEOS" with the GERG-2008
  mixture model, or `teqp` when T-07 lands — choose CoolProp here), `BWRSPackage` (Starling 1973,
  parameters for the 15 light-hydrocarbon/inert set from Starling's table, cited). Each refuses
  components outside its parameter set with the component named. CoolProp is imported lazily;
  without the extra the rows load as `status: experimental` with a clear message, never crash
  import.
- `data/thermo_models/helmholtz.yaml`: the 10 family-D rows.
- Tests (skipped cleanly without CoolProp): IAPWS-95 saturation pressure at 373.15 K within 1e-4
  relative and density of liquid water at 300 K / 1 bar within 1e-4 (IAPWS tables); IF97 vs 95
  agreement within 1e-3; GERG-2008 density of the GPSA natural-gas example mixture at 300 K / 10
  MPa within 0.1 % of the published AGA8/GERG value (cite); CoolProp pure methane Psat matches
  the harness's CoolProp regeneration path (it is the same library — assert identity); BWRS
  methane density at 300 K / 10 MPa within 1 % of NIST; L0 for every row.

## Acceptance criteria
- [ ] Rows load with and without CoolProp installed (status differs, nothing crashes)
- [ ] Reference tests pass with cited numbers; L0 green
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green; nothing outside the listed packages changed
