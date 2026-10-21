# T-12: Validation data sweep — gamma-phi family (B) and mixing-rule family (C)

- **Phase:** Thermo catalogue, wave 1 (data-only; runs in parallel with the adapter specs)
- **Depends on:** T-01 (case schema and status rules)
- **Packages you may edit:** `data/validation/gamma_phi/` (new case files, the harness loads every `cases*.yaml` under `data/validation/`), `data/thermo_models/gamma_phi.yaml` **only the `validation:` lists and `status:` fields**, `docs/validation/` (generated)
- **Contract change:** no (`data/validation/` is a locked path: the orchestrator applies the `contract-change` label)
- **Benchmark delta expected:** none

## Goal
Layers L1 (pure), L2 (binary) and L3 (canonical case) for every row of the family, from open,
citable sources: open-literature isothermal/isobaric VLE: methanol/water, ethanol/water, acetone/chloroform, benzene/toluene, water/toluene LLE, MEG/water, TEG/water (Gmehling & Onken open examples, NIST TDE references, journal tables — cited per point).

## Rules
- Every case carries `source` (full citation: authors, year, journal/volume/page or handbook
  table, retrieval date), the quantity, units, and a tolerance set **before** running the model,
  per the P1-05 conventions in `data/validation/cases.yaml`.
- Pure-fluid references are regenerated from CoolProp through the harness, never hand-typed;
  binary and canonical references are hand-typed from the cited table.
- A model row may be promoted to `validated` only when L0–L3 pass; record the measured numbers in
  the PR body as a table (row id, layer, cases, pass/fail). Rows that fail stay `provisional` with
  the failing case kept as `xfail` with the measured value and a filed issue — never deleted.
- No model code changes; if a case exposes a model defect, file an issue with the reproduction
  and leave the case in place.

## Acceptance criteria
- [ ] Every row of the family has ≥ 4 L1 cases, ≥ 2 L2 binaries (where the model claims mixtures) and the family's L3 case; `docs/validation/<id>.md` regenerated
- [ ] `scripts/validate_properties.py --audit` green; full `pytest -rs` green
