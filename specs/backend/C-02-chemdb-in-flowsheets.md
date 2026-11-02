# C-02: Chemical database in the flowsheet path, multiphase Gibbs reactor

- **Phase:** 5
- **Depends on:** C-01
- **Packages you may edit:** `ngdesign.data`, `ngdesign.units._physics`, `ngdesign.units.reactors`, `ngdesign.chem`, `tests/`
- **Contract change:** no
- **Benchmark delta expected:** none; the slice and the bench flowsheets carry no reactions

## Goal
One source of formation data and one Gibbs solver. `data.formation` reads the species models of
the cited database instead of `thermo.Chemical`, `gibbs_minimum` delegates to the multiphase
solver, and `gibbs_multiphase` puts condensed phases into flowsheets.

## Intentional changes to results
Formation numbers move to ATcT and JANAF:
- electrolyser reversible voltage at 298.15 K: 1.22874 to 1.22886 V; pinned closed forms follow;
- `V1-WGS-*` CO at 1100 K: 0.25047 to 0.25102 against JANAF's 0.25058, within tolerance (ATcT against JANAF ΔfH°);
- `V1202-sulfur-recovery-gpsa` stage 0 extent: 0.00502 to 0.00550 against 0.00528, still an assessed miss;
- a species with no gas model now refuses in `data.formation`, where it used to reach
  databank estimates;
- `gibbs_minimum` inerts no longer enter the element budget.

## Acceptance criteria
- [x] `tests/e2e/test_slice.py` and the bench byte-identity tests unchanged
- [x] `gibbs_minimum`, `reaction_thermo` and `ln_keq` agree to 1e-9 on shared data
- [x] `gibbs_multiphase`: V1-CRACK-GIBBS within tolerance; energy closes on every thermal mode
