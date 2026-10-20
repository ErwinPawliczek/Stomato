# P1-01: Thermo contract v2 — properties, K-values, saturation, derivatives

- **Phase:** 1
- **Depends on:** P0-04 (one `CubicEOS` base), P0-06 (benchmark baseline)
- **Packages you may edit:** `ngdesign.contracts` (`plugins.py`, `stream.py`, new `thermo.py`), `ngdesign.thermo`, `tests/contracts/`, `tests/thermo/`, `tests/golden/test_thermo.py` **only to add cases** (orchestrator applies the `contract-change` label)
- **Contract change:** yes — `Thermo` protocol, `Phase`, `StreamState`
- **Benchmark delta expected:** none in this spec (column still uses PT flashes; P1-03 migrates it)

## Goal
Today the `Thermo` protocol is three flashes (`contracts/plugins.py:19-24`). Every consumer that
needs K-values, phase enthalpies, bubble/dew points or fugacities rebuilds them from extra PT
flashes (`units/column.py` `_ThermoBox`: ~12 flashes per stage per sweep) or bypasses the
contract (`thermo.Chemical("water")`, `Psat_IAPWS`). The property package must answer those
questions directly. The `thermo`-library phase objects already expose all of it
(`H, S, Cp, G, lnphis, fugacities, dlnphis_dT, dlnphis_dP, dlnphis_dns, rho_mass, mu, k, Z, MW`),
so this is mostly plumbing plus a robust saturation solver.

## Files
- Create: `src/ngdesign/contracts/thermo.py` — typed records (pydantic `Model`):
  - `PhaseProps`: `kind, mole_fraction, composition, molecular_weight, density, enthalpy, entropy,
    cp, gibbs, z_factor, viscosity|None, thermal_conductivity|None, ln_phi: dict[str,float]`.
  - `SaturationPoint`: `T, P, kind: Literal["bubble","dew"], incipient_composition`.
  - `PropertyDerivatives`: `dlnphi_dT, dlnphi_dP` per component for one phase (used by P1-03
    and the future EO solver).
- Edit: `src/ngdesign/contracts/stream.py`
  - `Phase` gains `enthalpy: float`, `entropy: float`, `cp: float`, `ln_phi: dict[str, float] = {}`
    (J/mol, J/(mol K), J/(mol K)). Existing fields unchanged. `mass_flow` no longer raises:
    when `phases` is empty it computes MW from `ngdesign.data.components()`.
  - Keep `COMPONENTS` and `_check_composition` **unchanged** (P1-02 owns them).
- Edit: `src/ngdesign/contracts/plugins.py` — `Thermo` protocol becomes:
  ```python
  class Thermo(Protocol):
      def flash_pt(self, z, T, P, molar_flow) -> StreamState: ...
      def flash_ph(self, z, P, H, molar_flow) -> StreamState: ...
      def flash_ps(self, z, P, S, molar_flow) -> StreamState: ...
      def flash_tvf(self, z, T, vf, molar_flow) -> StreamState: ...   # vf in [0,1]
      def flash_pvf(self, z, P, vf, molar_flow) -> StreamState: ...
      def bubble_point(self, z, *, T=None, P=None) -> SaturationPoint: ...  # exactly one given
      def dew_point(self, z, *, T=None, P=None) -> SaturationPoint: ...
      def k_values(self, z, T, P) -> dict[str, float] | None: ...  # None if single-phase
      def phase_props(self, composition, T, P, kind: PhaseKind) -> PhaseProps: ...
      def derivatives(self, composition, T, P, kind: PhaseKind) -> PropertyDerivatives: ...
      def pure_psat(self, cid, T) -> float | None: ...   # None above Tc
  ```
  Docstring rewritten: it is a *property package* protocol, not "Peng-Robinson package".
- Edit: `src/ngdesign/thermo/cubic.py` (+ `_state.py`) — implement every method for the cubic
  packages. `nrtl.py` implements the same surface (activity-based K and γ-φ enthalpies).
  - `phase_props` builds a single-phase object of the requested kind at (x, T, P) — no flash.
  - `k_values` = y/x from a PT flash when two-phase, else `None` (same semantics the column
    uses today so P1-03 is a drop-in).
  - Saturation: **do not** rely on `FlashVLN.flash(VF=…)` — it raises `IndexError` /
    `UnboundLocalError` on the slice feed (verified 2026-10-20). Implement bubble/dew with a
    bracketed secant on the PT flash's vapour fraction (bracket from pure-component `Psat`
    bounds, tolerance 1e-8 relative on the unknown, cap 60 iterations), and use `FlashVL`
    (two-phase, same EOS objects) as the fast path when the stability test reports no second
    liquid. Return `None`-equivalent errors as a typed `SaturationError` (new, in
    `contracts/thermo.py`) when no two-phase region exists (supercritical feed).
  - `flash_tvf` / `flash_pvf`: secant on the other variable through `flash_pt`; reuse the
    bubble/dew endpoints as the bracket.
  - Property cache: LRU (size 4096) keyed on `(package, sorted z rounded 1e-10, round(T,6),
    round(P,3))` for PT flashes and `phase_props`. Keep it inside the package instance.
- Tests:
  - `tests/contracts/test_thermo_protocol.py`: every registered thermo plugin is an instance of
    the new `Thermo` protocol (`runtime_checkable`).
  - `tests/thermo/test_saturation.py`: pure methane/ethane/propane/water bubble P at three T
    vs CoolProp `PropsSI('P','T',T,'Q',0,fluid)` within 2 % (cubic EOS accuracy), dew = bubble
    for a pure fluid within 1e-6 relative; binary C1/C3 bubble and dew points bracket the PT
    flash (`vf(bubble_T − 0.01 K) == 0`, `vf(dew_T + 0.01 K) == 1`); `flash_tvf(0.5)` round-trips
    through `flash_pt` to 1e-6 on vf.
  - `tests/thermo/test_phase_props.py`: `phase_props` on each phase of a two-phase PT flash equals
    the flash's own phase (H, S, Cp, ln φ within 1e-9); mixture H from phases equals
    `StreamState.enthalpy` within 1e-9 relative.
  - `tests/thermo/test_derivatives.py`: `dlnphi_dT` vs central finite difference of `ln_phi`
    (relative 1e-5).
  - `tests/golden/test_thermo.py`: **add** (do not modify existing) cases for bubble/dew vs
    CoolProp on the pure fluids above.

## Method
Thermodynamic identities are the oracle: Σ β_k H_k = H; for a pure fluid bubble ≡ dew;
`k_values` consistent with `exp(ln φ_L − ln φ_V)` within 1e-9 for cubics. All SI.
Cite: Michelsen & Mollerup, *Thermodynamic Models: Fundamentals and Computational Aspects*,
ch. 10 (saturation), for the algorithm.

## Acceptance criteria
- [ ] New protocol methods implemented by `pr`, `srk`, `pr78`, `nrtl`; protocol test passes for all
- [ ] All tests listed above PASS; existing `tests/golden/test_thermo.py` cases PASS unchanged
- [ ] `tests/e2e/test_slice.py` byte-identical (new `Phase` fields do not appear in rendered outputs — verify)
- [ ] `bench/baseline.json` flash counts unchanged (`scripts/bench_baseline.py --check`)
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green
- [ ] Nothing outside the listed packages changed

## Out of scope
Migrating the column (P1-03), open components (P1-02), new packages (UNIFAC/PC-SAFT), speed.
