# S0-3: Crude and vacuum columns at R2, and the S0 flowsheet against the Bagajewicz & Ji reference

- **Phase:** Unit catalogue round 2 (slice S0, crude refining), step 3.
- **Depends on:** S0-1 (column extensions, merged), S0-D (completed reference, merged #237), U-H1 (refining R0 units, merged #223, #233).
- **Packages you may edit:**
  - `src/ngdesign/units/refining/` (new R2 adapter modules only; the R0 adapters stay);
  - `data/unit_models/refining.yaml` (the R2 levels of `crude_column`, `vacuum_column` and `side_strip` only);
  - `data/validation_units/refining/` (append cases);
  - `src/ngdesign/flowsheets/` (one new S0 flowsheet module);
  - `tests/units/refining/`, `tests/e2e/` (new files only), generated `docs/units*`.
- **Never edit:** `units/column/` (S0-1 owns it; if an engine change is needed, stop and report it on the issue), `contracts/`, `thermo/`, `solver/`, `scripts/validate_units.py`, `units/catalogue.py`, `units/levels.py`, `tests/property/`, `data/validation_units/refining/s0_reference.yaml`.
- **GitHub issue:** see specs/INDEX.md (S0-3 row).
- **Contract change:** no.
- **Benchmark delta expected:** none for existing cases. Add an `s0` bench case only if the orchestrator asks in review.

## Target
The **complete plant** in the reference: [V1] Ji & Bagajewicz 2002, Table 5. It is the atmospheric column in the final **three-pumparound** light-crude design (34 trays, feed tray 29, draws on trays 1/9/16/25, three 4-tray side strippers, overflash 0.03, the printed steam ratios and pumparound duties), plus the 7-tray vacuum tower at 1.90 psia. Every configuration number comes from `s0_reference.yaml`; do not re-transcribe.

**The one assumption allowed:** the atmospheric column pressure is in the reference's `not_recorded`. Use a typical value from an open textbook (cite it), flag it in the flowsheet and the row note as *not from this unit*, and report the flash-zone T the model reaches at that pressure.

## Work
1. **crude_column R2.** An adapter over S0-1's `solve_column_full`. Products: overhead naphtha, kerosene, diesel and AGO (from the strippers), the atmospheric residue, and the water decant. It also exposes the stripping-steam inlets. Its ports must equal the row's ports (U-01c). If the R2 product set needs ports the R0 row lacks, extend the row's port list in this PR, with every port fed or produced at every level (R0 included); say so in the PR body.
2. **side_strip R2.** The coupled stripper section from S0-1, exposed as its own row level for flowsheets that draw it separately.
3. **vacuum_column R2.** MESH with pumparounds and no condenser: products are the vacuum overhead, LVGO, HVGO and the vacuum residue, with bottom steam. The wash zone is an R2 note: either model it as a draw/return pair or document it as out of scope, with the reason.
4. **The S0 flowsheet** (`flowsheets/s0.py`): assay feeder → (desalter R0) → preheat (shell_tube R0, fired_heater R0) → crude_column R2 → atmospheric residue → vacuum heater → vacuum_column R2. The specs are the reference's printed operating specs: product rates or D86 95 % points as the reference fixes them, and pumparound duties.

## Acceptance (fixed now, before any run)
- **Product rates** (m³/h at 15 °C, reference basis), each against [V1] Table 5: within **±2 % of the crude feed** (±15.9 m³/h) absolute.
- **D86 95 % points:** within **±8 °C** of the printed specs (naphtha 182, kerosene 271, diesel 327 °C), using the existing `data.assay` conversions.
- **Pumparound duties:** within **±10 %** of the printed duties (22.3/33.7/8.8 MW) when they are free variables. When they are specs, they are met to 1e-6.
- **Why these bands:** the reference is the authors' simulator result for a 48-pseudo characterisation we re-derive independently, so model-to-model scatter, not the printed rounding, sets the bands. They are fixed here and must not move after a run. A miss is recorded with its measured number in the case's `assessed` field and stays a miss.
- **Balances:**
  - V0 clean for the new levels, with the property rows passing and fast;
  - the whole flowsheet closes on mass and per component at 1e-6 of the feed;
  - energy closes against the reported duties.
- **Performance:** the S0 flowsheet solve takes under 5 minutes on a developer machine, and every test is under 60 s. No timeout raises. A slow flash goes to #234 with a profile, and its fix belongs at the thermo owner.
- **Gates:** ruff, ruff format, `mypy src tests` (strict), lint-imports, bench `--check` (identical counts for existing cases), harness `--audit`, CI green.

## Out of scope
The HEN and preheat-train optimisation ([P2]); desalter R1; fired heater R1; product property back-calculation beyond D86 95 %. Those are later S0 steps, pulled by this reference.
