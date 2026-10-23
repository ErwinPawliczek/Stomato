# A-01: Crude assay characterisation — distillation-curve conversions, light ends, cutting into pseudo-components, S0 reference data

- **Phase:** Unit catalogue, round 0 (crude refining slice S0, docs/unit-catalogue-plan.md §2 U-H, §2b)
- **Depends on:** P1-07 (flowsheet-owned `PseudoDefinition`, on main)
- **Packages you may edit:** `ngdesign.data` (new `assay.py`), `ngdesign.contracts` (new `assay.py` only — do not edit `flowsheet.py`, U-R owns it this round), `data/assays/`, `data/validation_units/refining/`, `tests/data/`
- **Contract change:** yes — new `Assay` model (not yet wired into `Flowsheet`; the U-H assay feeder does that in round 1)
- **Benchmark delta expected:** none
- **GitHub issue:** #193

## Goal
Petroleum feeds become pseudo-component slates from the measurements a refinery actually has: a
distillation curve, bulk gravity and light ends. This is the thermo-side foundation of the crude
slice; the atmospheric/vacuum column work in round 2 consumes its output unchanged.

## Files
- `contracts/assay.py`: `Assay` — `id`, `curve: DistillationCurve` (`kind ∈ {TBP, D86, D1160, D2887}`, basis `{LV%, wt%}`, points `(percent, T_K)`, `P_kPa` for D1160), bulk `api_gravity` or `sg`, optional `sg_curve` / `watson_k`, `light_ends: dict[cid, fraction]` (databank species, basis declared), optional bulk sulfur wt%, `provenance` (required). Validators: monotone curve, percent in [0,100], at least 3 points.
- `data/assay.py`:
  1. Conversions to TBP at 101.325 kPa, each a cited correlation implemented once: D86→TBP (Riazi & Daubert 1986, API Technical Data Book procedure 3A1.1), D2887→TBP (Daubert 1994 / API 3A3.1), D1160 → atmospheric-equivalent (Maxwell & Bonnell 1957, API 5A1.19) then D1160→TBP (API 3A2.1). Inverse TBP→D86 for product reporting. Every constant cited at its line; check each constant against the source table in the PR body (the thermo lesson: consistency tests do not catch a wrong constant).
  2. Curve interpolation/extrapolation to 0 and 100 % (Riazi 2005 distribution model, cited) — document the method.
  3. SG distribution: constant Watson K from bulk API and the curve's VABP/MeABP (API 2B2.1 / Riazi 2005 ch. 2), or a supplied sg curve.
  4. Cutting: `cut(assay, scheme)` with schemes `by_interval` (default 15 K to 700 K, 25 K to 811 K, 50 K above — state the source of the default) and `by_count`. Each cut → `PseudoDefinition(Tb = mid-percent TBP, sg)`; light ends kept as discrete databank components; returns the slate and mole/mass/volume fractions summing to 1 within 1e-12. Pseudo ids deterministic (`<assay id>_NBP<Tb_K>`).
- `data/assays/`: one example assay with open provenance (a published crude assay from a paper or a public government report — e.g. a US DOE/EIA or Environment Canada crude assay — never a proprietary Aspen/HYSYS/Haverly library entry).
- `data/validation_units/refining/s0_reference.yaml`: the S0 reference flowsheet — a published atmospheric (+ vacuum if available) crude unit with its assay, column configuration and product cut yields/temperatures, with full citation. Candidate: Bagajewicz & Ji 2001, Ind. Eng. Chem. Res. 40, 617. Record only the numbers a paper prints, with page/table references. If no openly citable complete reference is found, commit what exists and list the gaps explicitly in the file and the PR body.

## Method — tests (named, all PASS)
- `tests/data/test_assay.py`:
  - D86→TBP: reproduce a worked example from Riazi 2005 (ASTM MNL50) ch. 3 or the API TDB example to its printed rounding (cite example number and page);
  - D1160 at 10 mmHg → atmospheric equivalent reproduces the Maxwell–Bonnell worked example;
  - TBP→D86→TBP round trip within 0.5 K;
  - Watson K = (1.8·MeABP)^(1/3)/sg identity on a cut, and bulk API of the cut slate recombines to the input bulk API within 0.5 °API;
  - cutting conserves mass to 1e-12 and pseudo Tb/sg land inside their cut;
  - the example assay cuts into a slate that flashes with PR (one PT flash runs, no refusal) — the bridge to the thermo layer.
- No test asserts a value computed only by the code under test.

## Acceptance criteria
- [ ] Every correlation cited at its implementation line; worked-example tests reproduce the printed numbers
- [ ] Example assay and S0 reference committed with open provenance (gaps listed if any)
- [ ] ruff, ruff format, `mypy src tests`, lint-imports, full pytest green; bench byte-identical; openapi unchanged
- [ ] Nothing outside the listed packages changed

## Out of scope
The assay feeder unit and `Flowsheet` wiring (round 1, U-H); blending/product properties beyond D86 back-calculation; crude columns (round 2).
