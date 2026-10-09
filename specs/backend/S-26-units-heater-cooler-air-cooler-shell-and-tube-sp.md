# S-26: Units: heater, cooler, air cooler, shell-and-tube (spec outlet T)

- **Wave:** 1
- **Depends on:** S-01
- **Plugin:** kind `unit`, names `heater`, `cooler`, `air_cooler`, `shell_tube` (one class, four registrations)

## Goal
Heat exchange to a specified outlet temperature with pressure drop.

## Files (create only these)
- `src/ngdesign/units/heat_exchange.py`
- `tests/units/test_heat_exchange.py`

## Method
Ports inlet -> outlet. Params T_out (K), dP (Pa, default 0). Outlet = flash_pt(z, T_out,
P_in - dP); duty_W = F*(h_out - h_in). info: duty_kW. Optional param `duty_W` instead of T_out: then outlet
= flash_ph at h_in + duty/F.

## Acceptance criteria
- [ ] `tests/property/test_unit_balances.py` PASSES for all four names
- [ ] Own tests: cooling gives negative duty; duty spec and T_out spec agree on a round trip
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Two-stream exchanger rating (not in v1).
