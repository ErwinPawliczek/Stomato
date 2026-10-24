# U-H1: Refining separation and handling units, R0

- **Phase:** Unit catalogue round 1. Read `specs/backend/U-R1-round1-conventions.md` first.
- **Depends on:** U-00, U-01, A-01 (`ngdesign.data.assay`, `data/assays/`), P1-07 (pseudo-components)
- **Packages you may edit:**
  - `src/ngdesign/units/refining/` (new; you own the separation modules, and U-H2 adds reactor modules
    beside them);
  - `data/unit_models/refining.yaml` (R0 levels of the seven rows below only),
    `data/validation_units/refining/`;
  - `tests/units/refining/`, generated `docs/units*`.
- **GitHub issue:** #213
- **Contract change:** no
- **Benchmark delta expected:** none

## Pseudo-components (ruling)
Petroleum fractions are P1-07 `PseudoDefinition`s.
- **Source of the slate.** It comes from `ngdesign.data.assay.cut(assay, scheme)`; the feeder never
  invents pseudos.
- **Helper.** Add `units/refining/slate.py::assay_slate(assay_id, scheme) -> (pseudo_definitions,
  composition)`. Flowsheet builders put its definitions into the flowsheet's own pseudo slate (P1-07).
- **Standalone runs.** `example_case` and V1 cases run outside a flowsheet, so they register the slate
  through the module-level `register_pseudo` default and say so in a comment.
- **Rule for every unit:** never read or write pseudo properties except through `component_record` and
  the thermo package.

## Units (all R0, `units/refining/`)
| id | R0 method | V1 oracle |
|---|---|---|
| assay_feeder | stream conditioner over the assay slate: one inlet `crude_in`, whose composition comes from `assay_slate` (`example_case` builds it from the assay), and one outlet at the given `T` and `P` with the inlet flow (so V0 balances); info: volume flow, API gravity and cut volumes from A-01; refuse a `crude_in` whose composition is not the declared assay slate | Bagajewicz & Ji (2001) light crude from `data/assays/`: cut volumes and API gravity back-calculated within A-01's measured tolerances |
| desalter | crude in and wash water in; desalted crude out and brine out. `water_carryover_frac` (BS&W in the desalted crude) and `salt_removal` (salt as a tracked component when present, otherwise reported only); the water split by component; isothermal at `T`, `dP` | closed-form; cite a desalter BS&W spec (e.g. 0.1–0.2 vol %) as the example |
| crude_column | cut-point fractionation: params `cut_points_K` (TBP) and product names; every pseudo assigned by its Tb (normal boiling point from `component_record`) to its cut, with an optional linear `overlap_K` band splitting a pseudo between neighbouring cuts; real light ends (C1–C4, H2O) to the overhead; products flashed at their given draw T and P; `stripping_steam` inlet optional (water to overhead); duty from the energy balance (one net duty at R0, documented) | Bagajewicz & Ji (2001) product cut ranges for the same crude: product volumes per cut against the paper's table within its rounding |
| vacuum_column | same as crude_column at the flash-zone `P` with no condenser; products: off-gas, LVGO, HVGO, residue | Bagajewicz & Ji (2001) vacuum section, if tabulated; else closed-form |
| side_strip | steam-stripped draw: per-pseudo Kremser stripping with `_physics/shortcut.kremser_fraction` (U-E, so build this unit only after U-E merges); `S_i = K_i·V/L`, with K from `thermo.k_values` at the stripper T and P and N given; steam in, stripped product out, vapour return out | Watkins *Petroleum Refinery Distillation* side-stripper example if open; else closed-form |
| preflash | composes the U-D `flash_drum` adapter, or the existing separator if U-D has not merged; it is a flash drum on an assay stream, with no own physics | closed-form against the flash_drum |
| blending | mixer physics (adiabatic PH mix of the inlets) plus property indices from per-inlet params (inlet streams carry no octane): RVP by the Chevron blending index `RVP^1.25` (volume basis), sulfur on a mass basis, octane and cetane linear by volume (the R0 simplification, documented, with the blending-value caveat), and a D86 point by volume-average temperature (R0, documented). Each rule is cited | Gary, Handwerk & Kaiser *Petroleum Refining* RVP blending example |

## Ordering
- Build in this order: assay_feeder, desalter, crude_column, vacuum_column, preflash, blending.
- Build side_strip last, after U-E's `shortcut.py` is on main.

## Out of scope
MESH-based columns (round 2, S0 R2); D86 and TBP back-calculation beyond A-01's functions; refinery
reactors (U-H2).
