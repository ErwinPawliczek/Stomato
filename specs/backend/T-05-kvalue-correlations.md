# T-05: Classic K-value correlations — Chao–Seader, Grayson–Streed, Braun K10, Lee–Kesler–Plöcker, ideal and Henry

- **Phase:** Thermo catalogue, wave 1
- **Depends on:** T-01
- **Packages you may edit:** `ngdesign.thermo` (new `kvalue.py`), `data/thermo_models/kvalue.yaml`, `data/thermo_params/kvalue/` (coefficient tables), `data/validation/kvalue/`, `tests/thermo/`
- **Contract change:** no
- **Benchmark delta expected:** none

## Goal
Family E: the refinery-era K-value methods every simulator still ships because hydrocarbon
hydrotreating and vacuum columns were designed on them. They are correlations, not equations of
state: K_i = ν_i γ_i / φ_i with published components. In-house, each under ~150 lines, sharing a
`KValuePackage` base that provides the flash (Rachford–Rice on K) and enthalpies from the
Lee–Kesler departures (T-02's option, imported from `options.py`).

## Files
- `thermo/kvalue.py`: `KValuePackage(ThermoSurfaceMixin)` with `k_model`: `chao_seader` (Chao &
  Seader 1961: ν from the Pitzer-type correlation, γ from regular-solution theory with solubility
  parameters, φ from Redlich–Kwong), `grayson_streed` (Grayson & Streed 1963 coefficients, extended
  range), `braun_k10` (Braun convergence-pressure K10 charts digitised as the published polynomial
  fits, cite source), `lee_kesler_plocker` (Plöcker, Knapp & Prausnitz 1978 mixing rules on the
  Lee–Kesler EOS — this one is an EOS; implement the LK corresponding-states tables), `ideal`
  (Raoult with Antoine/`chemicals` Psat), `henry_ideal` (Henry's law for the light gases from the
  Sander 2015 table already used by the amine package, Raoult for the rest). Solubility parameters
  and molar volumes for the curated slate from Prausnitz (cite).
- `data/thermo_models/kvalue.yaml`: 10 rows with applicability (Chao–Seader: T 200–530 K, P ≤ 14
  MPa, hydrocarbons; Grayson–Streed: to 730 K / 20 MPa; BK10: low pressure vacuum/atmospheric).
- Tests: Chao–Seader and Grayson–Streed reproduce the worked example in Seader, Henley & Roper
  (Separation Process Principles, ch. 2 example on the Chao–Seader K-values) within 5 %; BK10 K
  for propane at 1 bar / 300 K within 10 % of the chart value (cite the chart reading); LKP density
  for the GPSA natural-gas example within 2 %; `ideal` equals Psat/P exactly; L0 for every row
  (the pure limits hold by construction; verify).

## Acceptance criteria
- [ ] 10 rows load; worked-example tests pass with cited numbers; L0 green
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green; nothing outside the listed packages changed
