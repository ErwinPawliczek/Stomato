# T-10: Solids, polymers and special chemistry — ideal solids and solubility products, Flory–Huggins and polymer NRTL/SAFT/UNIFAC-FV, HOC dimerisation, HF hexamerisation

- **Phase:** Thermo catalogue, wave 3
- **Depends on:** T-03 (gamma-phi, virial HOC), T-07 (teqp for polymer PC-SAFT), T-01
- **Packages you may edit:** `ngdesign.thermo` (new `special.py`), `ngdesign.contracts` (`stream.py`: a `SOLID` PhaseKind — contract change), `data/thermo_models/special.yaml`, `data/thermo_params/special/`, `data/validation/special/`, `tests/thermo/`, `tests/contracts/`, `openapi.json` + `schema.d.ts`
- **Contract change:** yes — `PhaseKind.SOLID` (orchestrator applies `contract-change`)
- **Benchmark delta expected:** none

## Goal
Family H: the methods a simulator needs for crystallisers, polymer streams and the two classic
vapour-phase association cases. Small each; the contract change (a solid phase on `StreamState`)
is the main work and must not disturb any existing consumer (solids absent → identical JSON).

## Files
- `contracts/stream.py`: `PhaseKind.SOLID`; validators accept it; every existing unit ignores it
  (a unit receiving a solid phase it cannot handle raises a typed error naming the unit).
- `thermo/special.py`: `IdealSolidPackage` (pure solid phases with solubility product / ideal
  solubility from ΔH_fus and T_m via `chemicals`; eutectic-free first version), `FloryHugginsPackage`
  (χ parameter per pair, cited), `PolymerNRTLPackage` (Chen 1993 segment-based NRTL),
  `PolymerPCSAFT` (through the T-07 bridge with segment parameters), `UNIFACFVPackage` (Oishi &
  Prausnitz 1978 free-volume UNIFAC), `HOCDimerisation` (carboxylic acids via the T-03 virial
  machinery with the chemical-theory correction, Hayden & O'Connell 1975), `HFHexamer` (Schotte
  1980 / the hexamer chemical-theory model for HF).
- Tests: naphthalene solubility in benzene at 25 °C vs Prausnitz (ideal solubility) within 5 %;
  Flory–Huggins polystyrene/toluene activity vs a cited point within 5 %; acetic acid vapour
  apparent molar mass at 400 K / 1 bar within 3 % of the HOC prediction (cite); HF vapour
  compressibility at 300 K vs the published hexamer-model value within 5 %; round-trip JSON with a
  SOLID phase; every existing golden and e2e byte-identical.

## Acceptance criteria
- [ ] `PhaseKind.SOLID` added without changing any existing serialised output; openapi/schema regenerated, frontend `check:api`/`typecheck` green
- [ ] Literature tests pass with cited numbers; L0 on each row's applicability
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green; nothing outside the listed packages changed
