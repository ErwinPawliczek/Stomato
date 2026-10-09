# S-27: Unit: centrifugal pump

- **Wave:** 1
- **Depends on:** S-01
- **Plugin:** kind `unit`, name `pump`

## Goal
Raise liquid pressure.

## Files (create only these)
- `src/ngdesign/units/pump.py`
- `tests/units/test_pump.py`

## Method
Ports inlet -> outlet. Params P_out (Pa), eta (default 0.65). Volumetric flow from liquid
density; shaft power = Q*dP/eta (use the S-08 function if merged, else inline). h_out = h_in + power/F;
outlet = flash_ph(z, P_out, h_out). power_W = shaft power. info: head_m, Q_m3_s.
Raise ValueError if vapor_fraction > 0.001.

## Acceptance criteria
- [ ] `tests/property/test_unit_balances.py` PASSES for pump
- [ ] Own tests: power matches Q*dP/eta within 1%
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Pump curves.
