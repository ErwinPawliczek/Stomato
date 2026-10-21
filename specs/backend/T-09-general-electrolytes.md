# T-09: General electrolytes — electrolyte-NRTL, Pitzer, extended UNIQUAC, sour water

- **Phase:** Thermo catalogue, wave 2 (hardest family; after T-03)
- **Depends on:** T-03 (gamma-phi adapter: vapour models and the NRTL machinery), T-01
- **Packages you may edit:** `ngdesign.amine` (`electrolyte.py` new — the amine package already owns the speciation pattern and the layer may import thermo), `data/thermo_models/electrolyte.yaml` (rows beyond the two amine ones), `data/thermo_params/electrolyte/`, `data/validation/electrolyte/`, `tests/thermo/`
- **Contract change:** no
- **Benchmark delta expected:** none (`amine_ke`, `amine_enrtl` byte-identical)

## Goal
Family G beyond amines: aqueous strong and weak electrolytes (NaCl, NaOH, H2SO4, NH3/CO2/H2S sour
water, mixed amines, physical-solvent co-absorption) with ion speciation, the long-range
Pitzer–Debye–Hückel term and a short-range model (NRTL or UNIQUAC). Build on the existing
`AmineReactivePackage` structure (speciation equilibria solved to a fixed point; typed
`AmineChemistryError`), generalised to arbitrary reaction sets declared as data.

## Files
- `amine/electrolyte.py`: `ElectrolytePackage(ThermoSurfaceMixin)` with `model`: `enrtl` (Chen et
  al. 1982/1986 electrolyte-NRTL: PDH + Born + local composition; the published τ for the
  water/NaCl and water/NH3/CO2 systems), `pitzer` (Pitzer 1973/1991 with the β0/β1/Cφ tables for the
  common salts, cited), `ext_uniquac` (Thomsen & Rasmussen 1999, parameters for the NaCl/Na2SO4
  systems), `sour_water` (the API Sour Water (Wilson) correlation already partly used by T-02's
  `sour` option: NH3/H2S/CO2 speciation). Reactions and equilibrium constants as data under
  `data/thermo_params/electrolyte/reactions.yaml` with citations; speciation by a damped
  Newton on the charge-balance/mass-balance set (one owner, reused by the amine package where
  possible — do not duplicate the amine speciation solver, import it).
- `data/thermo_models/electrolyte.yaml`: the family-G rows beyond the two existing ones.
- Tests: NaCl/water mean activity coefficient at 25 °C vs Robinson & Stokes table within 2 % at
  0.1, 1, 3 molal (eNRTL and Pitzer); water activity / osmotic coefficient likewise; NaCl
  solubility 6.1 molal at 25 °C within 3 %; sour-water H2S partial pressure over a NH3/H2S
  solution at 90 °C vs the API/Edwards et al. 1978 point within 10 %; `amine_ke`/`amine_enrtl`
  byte-identical; L0 on the aqueous-liquid applicability.

## Acceptance criteria
- [ ] Rows load; literature tests pass with cited numbers; amine packages byte-identical
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green; nothing outside the listed packages changed
