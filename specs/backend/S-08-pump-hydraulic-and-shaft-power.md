# S-08: Pump hydraulic and shaft power

- **Wave:** 0
- **Depends on:** none
- **Plugin:** kind `correlation`, name `pump_power`

## Goal
Implement the `pump_power` correlation as a callable plugin. Golden cases already exist in `data/golden/pump_power.yaml`.

## Files (create only these)
- `src/ngdesign/sizing/pump_power.py`
- `tests/sizing/test_pump_power.py`

## Method
P_hyd = Q*dP, P_shaft = P_hyd/eta (0 < eta <= 1).

Also provide `npsh_available(P_suction_Pa, P_vapor_Pa, rho, static_head_m, friction_head_m) -> m` = (P_s - P_vp)/(rho*g) + z - h_f, g = 9.80665, with its own tests.

Call signature: `__call__(self, **inputs)` taking exactly the `inputs` keys of the golden file, returning a dict with every `expected` key. Also expose a plain typed function for reuse by other modules (e.g. `def pump_power(...) -> ...`).

## Acceptance criteria
- [ ] `tests/golden/test_correlations.py -k pump_power` PASSES for every case (none skipped)
- [ ] Own tests: invalid input raises ValueError (negative/zero where physical), plus one hand-checked case
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Anything beyond this correlation.
