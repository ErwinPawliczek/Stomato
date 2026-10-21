# T-06: Predictive gE mixing rules on the cubic adapter — PSRK, VTPR, MHV1/MHV2, Wong–Sandler, Huron–Vidal, LCVM, SR-POLAR

- **Phase:** Thermo catalogue, wave 2
- **Depends on:** T-02 (cubic options), T-03 (gamma-phi: the gE models and UNIFAC group data)
- **Packages you may edit:** `ngdesign.thermo` (new `mixing_rules.py`; `cubic.py` only for the `mixing_rule` option hook), `data/thermo_models/mixing.yaml`, `data/validation/mixing/`, `tests/thermo/`
- **Contract change:** no
- **Benchmark delta expected:** none (the van der Waals one-fluid rule stays the default; existing rows byte-identical)

## Goal
Family C: a cubic EOS whose mixture parameter `a` is tied to a gE model at a reference pressure,
so polar systems at high pressure (CO2/methanol, water/alkanes, supercritical extraction) get
UNIFAC/NRTL quality without binary k_ij. The `thermo` library ships the EOS classes and the gE
models but not these mixing rules; they are literature-exact in-house code.

## Files
- `thermo/mixing_rules.py`: a `MixingRule` interface the cubic adapter calls for `a_mix`, `b_mix`
  and their composition derivatives (needed for fugacity coefficients): `vdw1` (default, the
  existing behaviour, exactly), `huron_vidal` (Huron & Vidal 1979, infinite-pressure reference),
  `mhv1` and `mhv2` (Michelsen 1990; Dahl & Michelsen 1990, zero-pressure reference with the q1/q2
  constants per EOS), `wong_sandler` (Wong & Sandler 1992, second-virial consistency with the
  k_ij-free form), `psrk` (Holderbaum & Gmehling 1991: SRK + Mathias–Copeman alpha + MHV1-type
  rule + PSRK UNIFAC groups from `thermo.unifac` PSRKSG), `vtpr` (Ahlers & Gmehling 2001:
  volume-translated PR + modified-UNIFAC Dortmund groups without the combinatorial term), `lcvm`
  (Boukouvalas et al. 1994, λ = 0.36 linear combination), `sr_polar` (Schwartzentruber & Renon
  1989, polar SRK with the composition-dependent k_ij form). The gE objects come from T-03's
  adapter (`GammaPhiPackage` exposes its liquid gE model); fugacity coefficients are implemented
  analytically for `a_mix` composition derivatives — verify against finite differences in a test.
- `data/thermo_models/mixing.yaml`: 9 rows (family C) with applicability `polar: true`, high pressure.
- Tests: `vdw1` reproduces `pr` and `srk` bit-for-bit (same flasher output on the slice feed);
  analytic ∂(n a)/∂n_i vs central finite differences within 1e-8 relative for a ternary; PSRK
  reproduces the CO2/methanol bubble pressure at 313 K within 5 % of the Holderbaum & Gmehling
  1991 figure (cite the read value); MHV2 vs Wong–Sandler on ethanol/water at 1 bar agree with the
  gamma-phi NRTL/ideal row within 1 K on the azeotrope; L0 for every row.

## Acceptance criteria
- [ ] 9 rows; `vdw1` default bit-identical for existing rows (bench, e2e, goldens unchanged)
- [ ] Derivative test and literature tests pass with cited numbers; L0 green
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green; nothing outside the listed packages changed
