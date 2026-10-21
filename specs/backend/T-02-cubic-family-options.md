# T-02: Cubic family — every thermo cubic class, alpha functions, volume translation, Boston–Mathias, sour terms

- **Phase:** Thermo catalogue, wave 1 (parallel with T-03/T-04/T-05/T-07)
- **Depends on:** T-01
- **Packages you may edit:** `ngdesign.thermo` (`cubic.py`, `options.py`, `_state.py` only for the option hooks named below), `data/thermo_models/cubic.yaml`, `data/validation/cubic/` (new cases), `tests/thermo/`
- **Contract change:** no
- **Benchmark delta expected:** none for `pr`, `pr78`, `srk` (byte-identical counts and results); new rows add no bench case

## Goal
Family A of `docs/thermo-catalogue-plan.md`: 25 named cubic methods from one adapter. The
`thermo` library ships PRMIX, PR78MIX, SRKMIX, RKMIX, VDWMIX, PRSVMIX, PRSV2MIX, TWUPRMIX,
TWUSRKMIX, APISRKMIX; the rest are options on them.

## Files
- `thermo/options.py`: implement the option objects T-01 declared. `AlphaFunction`: `default`,
  `twu` (Twu et al. 1995, three parameters per component from `chemicals`/literature, else fall
  back with provenance "fitted-from-omega" via the Twu generalised form), `mathias_copeman`
  (Mathias & Copeman 1983, parameters where published, else default alpha), `boston_mathias`
  (Boston & Mathias 1980 supercritical extrapolation). `VolumeTranslation`: `none`, `peneloux`
  (Péneloux et al. 1982, c from the Rackett Z_RA; affects density only, never VLE — assert that in
  a test). `LiquidDensity`: `eos`, `rackett`, `costald` (Hankinson & Thomson 1979), `api`. `EnthalpyMethod`:
  `eos`, `lee_kesler` (Lee & Kesler 1975 departures). `SourTerm`: `none`, `sour` (Wilson's API
  sour-water H2S/NH3/CO2 ionisation correction on the aqueous phase, API Publication 955).
- `thermo/cubic.py`: `CubicEOS` reads `options` from the catalogue row; the flasher key includes
  every option (two rows never share a flasher). Alpha and translation are applied through the
  `thermo` EOS kwargs where the library supports them (`alpha_coeffs`, `cs`), in-house otherwise.
- `data/thermo_models/cubic.yaml`: 25 rows exactly as listed in family A of the plan; each with
  applicability, references and `status: provisional` until its L1/L2 cases exist (T-11 adds the
  data; this spec adds the L0 pass and the cases it can source itself: at least pure-C1/C3/nC4/CO2
  Psat and density for every row via the CoolProp regeneration path the harness already has).
- Tests: every row builds and passes L0; `peneloux` changes liquid density but not bubble/dew P
  (assert equality to 1e-10 on the C1/C3 binary); `twu` alpha reproduces the Twu 1995 table for
  methane within 1 %; `boston_mathias` agrees with `default` below Tc and is finite above Tc where
  `default` alpha goes negative; `lee_kesler` enthalpy departure for methane at 300 K / 5 MPa within
  2 % of the NIST WebBook value (cite the number); `sour` reproduces the API 955 H2S partial
  pressure over water within 10 % at one published point.

## Acceptance criteria
- [ ] 25 rows in the catalogue, all L0 green; `pr`, `pr78`, `srk` byte-identical (bench, e2e, goldens)
- [ ] Option tests above pass with cited numbers; `docs/validation/<id>.md` generated for every row
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green; nothing outside the listed packages changed
