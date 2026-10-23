# U-E: Shortcut column units, R0

- **Phase:** Unit catalogue round 1. Read `specs/backend/U-R1-round1-conventions.md` first.
- **Depends on:** U-00, U-01, P1-11 (merged)
- **Packages you may edit:**
  - `src/ngdesign/units/column_shortcut/` (new);
  - `src/ngdesign/units/_physics/shortcut.py` (new; you own it);
  - `data/unit_models/column.yaml` (R0 levels of the four rows below only), `data/validation_units/column/`;
  - `tests/units/column_shortcut/`, generated `docs/units*`.
- **Never edit `units/column/`.** You may import from it, read-only, in tests.
- **GitHub issue:** #210
- **Contract change:** no
- **Benchmark delta expected:** none

## Shared physics first: `_physics/shortcut.py`
Each function below has its equation number and source in the docstring:
- `fenske_nmin(alpha_LK_HK, xD_LK, xD_HK, xB_LK, xB_HK)`.
- `underwood_theta(alphas, z, q)`: the root between α_HK and α_LK, bracketed and refused when not
  bracketed.
- `underwood_rmin(alphas, xD, theta)`.
- `gilliland(R, Rmin, Nmin)`: the Molokanov et al. (1972) form `Y = 1 − exp[(1+54.4X)/(11+117.2X)·(X−1)/√X]`.
  Constants are checked against Seader–Henley.
- `kirkbride(...)`.
- `kremser_fraction(A, N)`: the fraction absorbed `(A^(N+1) − A)/(A^(N+1) − 1)`, with the A → 1 limit
  N/(N+1). It is the inverse form of `sizing.kremser`. Pin it with a round-trip test against
  `sizing.kremser`: φ from N, then N back from φ.

Relative volatilities come from `thermo.k_values` at the feed and at the estimated top and bottom
conditions, using the geometric mean (documented).

## Units (all R0, `units/column_shortcut/`)
| id | R0 method | V1 oracle |
|---|---|---|
| shortcut_distillation | FUG: params `light_key`, `heavy_key`, `recovery_LK_D`, `recovery_HK_B`, `R_over_Rmin` (or `R`), `P_top`, `P_bottom`, condenser `total`/`partial`. Non-key distribution by Fenske at Nmin (Hengstebeck–Geddes). Distillate at its bubble point (total condenser) or dew point (partial); bottoms at its bubble point. Condenser and reboiler duties from the energy balance (`duty_W` = reboiler − condenser, and both in info). Info: `Nmin`, `Rmin`, `R`, `N`, `feed_stage` | Seader–Henley (3rd ed.) Examples 9.x FUG on a hydrocarbon feed: Nmin, Rmin and N within the book's rounding |
| absorber | Kremser on each component at R0: `A_i = L/(K_i·V)` at the average of the inlet T and P (documented); fraction absorbed `kremser_fraction(A_i, N)` with `N` given; an isothermal model at R0 (outlets at the given T, with the duty reported); ports gas_in, solvent_in, gas_out, rich_out | Seader–Henley Example 6.x (Kremser absorber, hydrocarbon/oil); P1-09 measured Kremser vs zero-tear MESH within 2 % |
| reboiled_stripper | the Kremser stripping form `S_i = K_i·V/L` with steam or vapour-boilup flow given; same structure as absorber | Seader–Henley stripping example |
| liquid_liquid_extractor | the Kremser extraction form `E_i = K_D,i·S/F`, with distribution coefficients from the package's LLE `k_values` (refuse when the package gives no second liquid) or given `K_D` in params | Treybal / Seader–Henley Kremser extraction example |

## V2 (mandatory in this family)
- **FUG vs MESH.** `shortcut_distillation` N at the solved R against the `column` R2 MESH on the
  deethanizer bench case at the same reflux and key recoveries. The test records the measured stage
  difference and asserts it is inside the Gilliland correlation's published scatter (±20 % on N, cited);
  a miss is recorded with its number.
- **Kremser vs MESH.** The `absorber` R0 against the `column` R2 zero-tear configuration on the P1-09
  absorber case, within 2 % on the key-component recovery, as P1-09 measured.

## Out of scope
R2 rows (absorber/stripper on MESH via the `column` adapter); internals hydraulics; three-phase stages.
