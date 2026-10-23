# U-G: Treating units, R0 (TEG regenerator, Claus sulfur recovery)

- **Phase:** Unit catalogue round 1. Read `specs/backend/U-R1-round1-conventions.md` first.
- **Depends on:** U-00, U-R, U-01
- **Packages you may edit:**
  - `src/ngdesign/units/treating/` (new);
  - `data/unit_models/treating.yaml` (the `teg_regen` and `sulfur_recovery` R0 levels only),
    `data/validation_units/treating/`;
  - `tests/units/treating/`, generated `docs/units*`.
- **Never edit:** `units/teg_*.py`, `units/mdea_*.py`, `amine/`. Import from them.
- **GitHub issue:** #212
- **Contract change:** no
- **Benchmark delta expected:** none

## Units (R0, `units/treating/`)
| id | R0 method | V1 oracle |
|---|---|---|
| teg_regen | rich TEG in (plus an optional stripping gas in), lean TEG out plus overhead vapour out, at reboiler `T_reboiler` and `P`. Lean TEG purity follows the reboiler T at atmospheric pressure from the TEG–water equilibrium of the existing `units/teg_activity.py` (one owner), with the stripping-gas enhancement as a cited correlation (GPSA Fig. 20-x lean-glycol concentration vs stripping-gas rate) or refused when not cited. Water and absorbed light components go overhead. Reboiler duty comes from the energy balance | GPSA EDB Sect. 20 TEG regeneration example (lean wt % at 204 °C, about 98.6–98.9 wt %) |
| sulfur_recovery | Claus. Thermal stage: one third of the H2S burned to SO2 (`H2S + 1.5 O2 → SO2 + H2O`, with the air rate from that stoichiometry or given), then `2 H2S + SO2 → (3/x) S_x + 2 H2O` at a given thermal-stage conversion. N catalytic stages, each at a given equilibrium approach or conversion. Sulfur is condensed out after each stage to a `sulfur_out` port. `balance: mass_elements` | GPSA Sect. 22 / Kohl & Nielsen ch. 8 Claus example (overall recovery about 94–97 % for 2 to 3 stages) |

For `sulfur_recovery`:
- Use the U-R reaction contract and `kinetics.apply_extents`; the reaction set is inline in params, like
  U-F's (a).
- Sulfur allotropes: use whichever `S2`/`S6`/`S8` species have formula and formation data in the databank,
  and record the choice. If none is usable, the unit refuses with the measured reason and the row stays
  planned. Document this.

## Notes
The plan's U-G rows for mol-sieve dehydration (that is U-D `adsorption_bed`), the LNG and NGL templates
(flowsheets, not units) and the sour-water stripper (it needs the T-09 electrolyte package on a reboiled
stripper) are not catalogue rows. Leave them, and list them in the PR body.

## Out of scope
Staged TEG (R2); Claus Gibbs stages (R2); tail-gas treating.
