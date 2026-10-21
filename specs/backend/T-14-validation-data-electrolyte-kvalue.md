# T-14: Validation data sweep — electrolyte family (G), K-value family (E) and special family (H)

- **Phase:** Thermo catalogue, wave 2 (data-only)
- **Depends on:** T-01 (schema and status rules)
- **Packages you may edit:** `data/validation/electrolyte/`, `data/validation/kvalue/`, `data/validation/special/` (new case files), `data/thermo_models/{electrolyte,kvalue,special}.yaml` **only the `validation:` lists and `status:` fields**, `docs/validation/` (generated)
- **Contract change:** no (`data/validation/` is locked: the orchestrator applies `contract-change`)
- **Benchmark delta expected:** none

## Goal
L1–L3 cases from open sources: Robinson & Stokes activity-coefficient tables, Pitzer's compiled
osmotic coefficients, Edwards et al. 1978 sour-water VLE, Kohl & Nielsen amine loading isotherms
(the P1-04 bands), GPSA and Perry refinery flash examples for the K-value correlations, Prausnitz
solubility examples for solids, Danner & High polymer solution data for family H — every point
cited with authors, year, journal volume/page or handbook table, and retrieval date.

## Rules
Same as T-11..T-13: tolerances fixed before running; pure references via the harness's CoolProp
path; hand-typed binaries; `pending:<id>` convention for models not yet on main; failing cases stay
as `xfail` with the measured value and a filed issue; no model code changes.

## Acceptance criteria
- [ ] Every row of G, E and H has ≥ 4 L1 cases, ≥ 2 L2 cases where mixtures are claimed, and its family's L3 case; `docs/validation/<id>.md` regenerated
- [ ] `scripts/validate_properties.py --audit` green; full `pytest -rs` green
