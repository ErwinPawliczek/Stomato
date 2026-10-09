# S-29: Unit: TEG contactor (spec-based)

- **Wave:** 1
- **Depends on:** S-01, S-05
- **Plugin:** kind `unit`, name `teg_contactor`

## Goal
Dehydrate gas to a water spec with lean TEG; estimate stages with Kremser.

## Files (create only these)
- `src/ngdesign/units/teg_contactor.py`
- `tests/units/test_teg_contactor.py`

## Method
Ports gas_in, lean_teg_in -> gas_out, rich_teg_out. Param water_out_lb_per_mmscf (default 7).
Water removed = inlet gas water - spec (convert lb/MMscf with 379.49 scf/lbmol). gas_out = gas_in minus that
water (and no TEG losses in v1); rich_teg_out = lean TEG + removed water. Flash both outlets at gas_in T, P.
duty_W = sum(H_out*F) - sum(H_in*F) (heat of absorption/mixing reported, not modelled).
info: water_removed_kg_h, teg_circulation_L_per_kg_water, N_stages (Kremser, S-05, with equilibrium slope m
taken as y*/x from a GPSA-style TEG/water equilibrium approximation: document the assumption).

## Acceptance criteria
- [ ] `tests/property/test_unit_balances.py` PASSES for teg_contactor
- [ ] Own tests: outlet water content equals spec within 1%; infeasible spec (water out > water in) raises
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Rigorous TEG/water VLE; regeneration (not in v1).
