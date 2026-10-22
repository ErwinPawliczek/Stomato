# T-03b: Virial vapour models — Hayden-O'Connell and Nothnagel for the gamma-phi rows

- **Phase:** Thermo catalogue, wave 3 (follow-up to T-03, PR #150)
- **Depends on:** T-03 (merged #150), T-02 (merged #161: the `assessed:` convention)
- **Packages you may edit:** `ngdesign.thermo` (`virial.py` — replace the refusal stub; `gamma_phi.py` only in `_gas_phase` and the vapour-model wiring), `data/thermo_models/gamma_phi.yaml` (the 24 `*_hoc` / `*_nothnagel` rows: status, validation, assessed), `data/thermo_params/virial/` (new), `data/validation/gamma_phi/` (rebind cases to the virial rows), `tests/thermo/`
- **Contract change:** no
- **Benchmark delta expected:** none (no bench case uses a virial vapour)

## Goal
Twenty-four of the sixty gamma-phi rows (every liquid model × `hoc` and × `nothnagel`) are
`experimental` refusal stubs because T-03 could not source the virial equation sets. The vapour
half of the gamma-phi product must be real: the second virial coefficient with the chemical-theory
correction for associating vapours (carboxylic acids, alcohols, water, HF-free) is the standard
low-pressure vapour model of every commercial simulator, and the HOC dimerisation row of T-10
(`hoc_dimer`) already carries the Marek–Standart kernel for the acetic-acid case.

## What exists
- `thermo.phases.VirialGas` with `VirialCSP` B-models: Tsonopoulos, Tsonopoulos-extended (polar
  a/b), O'Connell–Prausnitz, Pitzer–Curl, Abbott, Meng, Xiang; cross terms Tarakad–Danner. No
  Hayden–O'Connell, no Nothnagel.
- `chemicals.dipole` and `chemicals.RG` (radius of gyration) — the HOC inputs — for the curated
  components.
- `thermo/virial.py`: the refusal stub naming the two models; `gamma_phi._gas_phase` calls it.

## Files
- `thermo/virial.py`: `HaydenOConnellB` and `NothnagelB` as B-coefficient providers usable by a
  `VirialGas` phase (a `VirialCSP` subclass or an equivalent `model` object implementing the pure
  and cross `B(T)` the phase needs — read `thermo.phases.virial_phase` first and reuse its
  machinery; never re-implement fugacity coefficients the phase already derives from B).
  - Hayden & O'Connell (1975), AIChE J. 21, 510: free, metastable, bound and chemical
    contributions with the published constants; inputs Tc, Pc, dipole, radius of gyration from
    `chemicals`; association parameters η from Prausnitz, Anderson, Grens, Eckert, Hsieh &
    O'Connell (1980), reproduced in Poling, Prausnitz & O'Connell, *The Properties of Gases and
    Liquids*, 5th ed., Table 4-? (cite the table you read) — shipped in
    `data/thermo_params/virial/hoc_eta.yaml` with a citation per pair; a pair with no published
    η uses η = 0 (no association) and the row's `assessed:`/notes say so.
  - Nothnagel, Abrams & Prausnitz (1973), Ind. Eng. Chem. Process Des. Dev. 12, 25: the
    chemical-theory dimerisation model with the published `b` and `K` parameters; same provenance
    rules.
  - If either equation set cannot be transcribed from a citable open source, the fallback for
    that model is `thermo`'s Tsonopoulos-extended B with the published polar a/b constants, the
    row name says "Tsonopoulos (fallback)", and the deviation is declared — never a silent
    substitution.
- `gamma_phi.py::_gas_phase`: `hoc` and `nothnagel` build a `VirialGas` with the matching B
  provider; the ideal/RK/PR branches unchanged. Flash machinery, caches and refusals unchanged.
- `data/thermo_models/gamma_phi.yaml`: the 24 rows become `provisional` (or stay `experimental`
  with the fallback note), each with `validation:` bound to the T-12 cases the pairing can run
  and `assessed:` declarations with measured numbers for every miss.
- Tests (`tests/thermo/test_virial.py`): HOC B for acetic acid at 400 K against the HOC paper's
  worked value within 2 %; Nothnagel B for acetic acid within 2 % of the 1973 paper; water vapour
  B at 373 K within 3 % of the IAPWS value; `nrtl_hoc` reproduces the ethanol/water azeotrope
  within the T-03 tolerance; the `hoc_dimer` acetic-acid apparent-molar-mass check of #160 agrees
  with `nrtl_hoc`'s vapour within 1 % (two implementations of one physics must agree — if they do
  not, find out which is wrong, never widen).

## Acceptance criteria
- [ ] 24 rows build and flash; each row `provisional` or `experimental` with the reason; every
  failing case declared with its measured number; L0 green on every row
- [ ] The five literature tests pass with cited numbers
- [ ] bench byte-identical; ruff, mypy, lint-imports, full `pytest -rs`, audit PASS; reports regenerated

## Out of scope
Third virial coefficients, the HOC association for HF (T-10 #160 owns the hexamer), any change to
the liquid models.
