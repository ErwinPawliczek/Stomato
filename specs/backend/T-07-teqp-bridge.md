# T-07: teqp bridge — PC-SAFT, SAFT-VR Mie, CPA, multi-fluid Helmholtz

- **Phase:** Thermo catalogue, wave 1
- **Depends on:** T-01
- **Packages you may edit:** `ngdesign.thermo` (new `teqp_bridge.py`), `data/thermo_models/saft.yaml`, `data/thermo_params/saft/` (pure-component parameters with citations), `data/validation/saft/`, `tests/thermo/`, `pyproject.toml` + `uv.lock` **only to add the optional extra `saft = ["teqp>=0.22"]`** (orchestrator applies the `contract-change` label)
- **Contract change:** no
- **Benchmark delta expected:** none

## Goal
Family F through NIST's `teqp` (MIT licence): do not write SAFT by hand. `teqp` exposes PC-SAFT,
SAFT-VR Mie, CPA and multi-fluid Helmholtz models with a uniform residual-Helmholtz API; the
bridge supplies the ideal-gas part from `chemicals` heat capacities and runs the flash on
`teqp`'s derivatives.

## Files
- `thermo/teqp_bridge.py`: `TeqpPackage(ThermoSurfaceMixin)` with `model`: `pc_saft`, `pc_saft_polar`,
  `saft_vr_mie`, `cpa_srk`, `cpa_pr`, `multifluid`. PT flash: stability analysis + two-phase
  Rachford–Rice on `teqp` fugacity coefficients (the bridge owns the flash loop since `teqp` has no
  general VLN driver; three-phase out of scope, declare `phases: [V, L]`). Enthalpy/entropy from
  `teqp` residual derivatives plus ideal-gas integrals. Lazy import; rows load as `experimental`
  without the extra.
- `data/thermo_params/saft/pure.yaml`: PC-SAFT parameters for the curated slate from Gross &
  Sadowski 2001 (and 2002 for associating water/alcohols), SAFT-VR Mie from Lafitte et al. 2013 /
  Dufal et al. 2015 where published, CPA from Kontogeorgis et al. (water, MEG, MeOH) — every row
  cited; components without parameters are refused by name.
- `data/thermo_models/saft.yaml`: 8 rows.
- Tests (skipped cleanly without teqp): PC-SAFT methane Psat at 150 K within 2 % and liquid density
  within 2 % of NIST; CPA-SRK water Psat at 373 K within 1 %; PC-SAFT CO2/methane bubble pressure
  at 230 K vs the published point within 5 % (cite); L0 for every row.

## Acceptance criteria
- [ ] Rows load with and without teqp; tests pass with cited numbers; L0 green
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green; nothing outside the listed packages changed
