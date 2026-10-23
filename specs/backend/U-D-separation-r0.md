# U-D: Phase-separation units, R0

- **Phase:** Unit catalogue round 1. Read `specs/backend/U-R1-round1-conventions.md` first.
- **Depends on:** U-00, U-01. `hydrocyclone`, `filter` and `membrane` also depend on U-A1
  (`units/_physics/splitting.py`); build them only after it is on main, and do the other five first.
- **Packages you may edit:**
  - `src/ngdesign/units/separation/` (new);
  - `data/unit_models/separation.yaml`, `data/validation_units/separation/`;
  - `tests/units/separation/`, generated `docs/units*`.
- **GitHub issue:** #209
- **Contract change:** no
- **Benchmark delta expected:** none. `scrubber` and `separator_3phase` stay untouched.

## Units (all R0, `units/separation/`)
| id | R0 method | V1 oracle candidates |
|---|---|---|
| flash_drum | one or more inlets mixed, then one of: PT flash, PH flash with `duty_W`, or P plus `vapor_fraction`; vapour and liquid outlets (plus aqueous when the package gives a second liquid); `duty_W` reported | Seader–Henley *Separation Process Principles* isothermal flash example (Rachford–Rice); Smith–Van Ness–Abbott flash example |
| decanter | LLE split: PT flash at the decanter T and P; the two liquid phases go to the light and heavy outlets; refuse (typed) when the package returns a single liquid, naming T and P | Seader–Henley LLE / ternary example; Treybal |
| tank | steady state equals a mixer: adiabatic PH mix of the inlets at `P = min inlet P` (or a given P); params `volume_m3`; info `residence_time_s` from the liquid volumetric flow (`thermo.phase_props` density) | closed-form only |
| hydrocyclone | `splitting.split_by_component`; params `underflow_fractions` (per component, e.g. water from oil in a deoiling service) and `dP` on the overflow | Perry Sect. 18 cut-size example is R1, so closed-form only at R0 |
| filter | `splitting.split_by_component` with `cake_fractions` (solid-like components to cake) and `dP` | closed-form only |
| membrane | `splitting.split_by_component` with per-component `permeate_recovery` **or** `stage_cut` with relative permeances (`perm_ratio` to a reference component, complete-mixing closed form: Weller–Steiner complete-mixing model); permeate at `P_permeate`; refuse a stage cut ≥ 1 | Geankoplis / Seader–Henley complete-mixing membrane example (binary O2/N2) |
| adsorption_bed | two outlets, product and desorbate: `removal_fraction` per adsorbate component goes to desorbate; product and desorbate flashed at their own T and P; params `capacity_kg_per_kg`, `bed_mass_kg`; info `cycle_time_s` = capacity·mass / adsorbate mass rate | GPSA Sect. 20 mol-sieve dehydration sizing example (water loading and cycle time) |
| hydrate_check | gas inlet plus inhibitor inlet (MeOH or MEG), one outlet (an adiabatic PH mix); info: hydrate formation T from `sizing.hammerschmidt_formation` (or from the inlet's own correlation inputs), the depression from `sizing.nielsen_bucklin_suppression` at the aqueous inhibitor fraction, and the required inhibitor rate for a target `T_operating` | GPSA Sect. 20 methanol-injection example |

## Out of scope
Souders-Brown sizing (R1); Stokes settling; Lapple cut size; solution-diffusion; Langmuir isotherms.
