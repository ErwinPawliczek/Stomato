# S-25: Unit: compressor (isentropic efficiency)

- **Wave:** 1
- **Depends on:** S-01
- **Plugin:** kind `unit`, name `compressor`

## Goal
Compress gas to a set discharge pressure.

## Files (create only these)
- `src/ngdesign/units/compressor.py`
- `tests/units/test_compressor.py`

## Method
Ports inlet -> outlet. Params P_out (Pa), eta_isentropic (default 0.75).
s_in from inlet; isentropic outlet h_is = flash_ps(z, P_out, s_in).enthalpy; actual
h_out = h_in + (h_is - h_in)/eta; outlet = flash_ph(z, P_out, h_out). power_W = F*(h_out - h_in).
info: T_out_isentropic, pressure_ratio, polytropic_head_J_kg (Schultz approximation with average Z is fine).
Raise ValueError if the inlet has liquid (vapor_fraction < 0.999) or P_out <= P_in.

## Acceptance criteria
- [ ] `tests/property/test_unit_balances.py` PASSES for compressor
- [ ] Own tests: eta = 1 reproduces the isentropic outlet T; lower eta gives higher T_out and power
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Multistage with intercooling (not in v1).
