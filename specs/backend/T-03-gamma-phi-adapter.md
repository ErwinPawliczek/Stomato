# T-03: Gamma-phi adapter — activity-coefficient liquids × vapour models, with parameter databanks

- **Phase:** Thermo catalogue, wave 1
- **Depends on:** T-01
- **Packages you may edit:** `ngdesign.thermo` (new `gamma_phi.py`, new `virial.py`; `nrtl.py` becomes a thin row of the adapter), `data/thermo_models/gamma_phi.yaml`, `data/thermo_params/{nrtl,uniquac,wilson,unifac,vanlaar,margules}/` (new), `data/validation/gamma_phi/`, `tests/thermo/`
- **Contract change:** no
- **Benchmark delta expected:** none; the existing `nrtl` row stays byte-identical (`tests/thermo/test_nrtl*.py`, validation cases #100 family unchanged)

## Goal
Family B: 12 liquid models × 5 vapour models = 60 rows from one adapter. The `thermo` library
provides `GibbsExcessLiquid` with NRTL, UNIQUAC, Wilson, RegularSolution and the UNIFAC variants
(original, Dortmund, PSRK, NIST, LLE, Lyngby subgroup sets); van Laar and Margules are 30-line
in-house gE models on the same interface. Vapour: ideal gas, `VirialGas` with Hayden–O'Connell
(1975) and Nothnagel (1973) second virial coefficients (in-house `virial.py`, the published
correlations), and the cubic gas phases from family A.

## Files
- `thermo/gamma_phi.py`: `GammaPhiPackage(ThermoSurfaceMixin)` taking `liquid: str`, `vapour:
  str`, `params: ParameterSource`. Flash through `thermo.FlashVL`/`FlashVLN` with the gE liquid
  and the chosen gas; three-phase (LLE) enabled for the models that support it (UNIFAC-LLE, NRTL,
  UNIQUAC). Missing binary parameters are an error naming the pair (the existing NRTL rule) unless
  the row declares `missing_pairs: ideal` explicitly (UNIFAC never needs it; group assignment
  missing is also an error naming the component).
- `thermo/virial.py`: Hayden–O'Connell and Nothnagel B_ij with the published parameter tables for
  the curated slate (dipole moments, radii of gyration, association parameters from Prausnitz et
  al. 1980 / the `chemicals` databank where present), cited per table.
- `data/thermo_params/<model>/pairs.yaml`: binary parameters with citation per row. Sources:
  ChemSep (bundled in `thermo`'s IPDB) for NRTL/UNIQUAC/Wilson; UNIFAC group tables from
  `thermo.unifac`; van Laar/Margules from Gmehling & Onken (DECHEMA) *open* examples only, each
  cited. Group assignments for the curated slate for every UNIFAC variant.
- `data/thermo_models/gamma_phi.yaml`: 60 rows; applicability `polar: true`, `P_Pa` ceiling 1.5 MPa
  for ideal/virial vapour rows, higher for cubic-vapour rows; `status: provisional` until T-12 data.
- Tests: every row builds and passes L0 (Gibbs–Duhem on γ for MeOH/H2O at 1 bar; pure limits);
  NRTL/ideal reproduces the methanol/water azeotrope at 1 atm within 0.5 K and 0.01 in x (cite
  Gmehling & Onken vol. 1 part 1); UNIFAC-Dortmund ethanol/water azeotrope within 1 K; UNIFAC-LLE
  water/toluene mutual solubilities within 30 % (order-of-magnitude physics, cite Sørensen & Arlt);
  Hayden–O'Connell B for acetic acid dimerisation sign and magnitude at 400 K (cite); the existing
  `nrtl` row byte-identical.

## Acceptance criteria
- [ ] 60 rows, all L0 green; the azeotrope and LLE tests pass with cited numbers
- [ ] `nrtl` byte-identical; no silent ideal fallbacks (a planted missing pair raises naming the pair)
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green; nothing outside the listed packages changed
