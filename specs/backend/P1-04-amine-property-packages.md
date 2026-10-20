# P1-04: Amine chemistry as property packages (apparent-component reactive VLE)

- **Phase:** 1
- **Depends on:** P0-02 (amine package owns the chemistry), P1-01 (contract v2)
- **Packages you may edit:** `ngdesign.amine`, `ngdesign.thermo` (new `amine_ke.py`, `amine_enrtl.py` registrations only), `ngdesign.units` (only `mdea_absorber.py`, `mdea_regenerator.py` to consume the package), `tests/amine/`, `tests/thermo/`, `tests/units/`
- **Contract change:** no (uses the v2 `Thermo` protocol as is)
- **Benchmark delta expected:** amine_loop / mea_amine_loop: flash counts may change (state the new numbers; update `bench/baseline.json` with `--update`)

## Goal
The amine units are spec-driven and compute acid-gas split from Kent–Eisenberg / e-NRTL, but
their **outlet streams are flashed with the cubic EOS**, which knows nothing about the
chemistry: rich-amine enthalpy omits the heat of absorption, and any downstream unit (heat
exchanger, regenerator reboiler) sees wrong duties. The chemistry must live where every other
property lives — in a registered `thermo` package — so that streams, duties and (later) staged
columns are consistent. Ions never leave the package: the stream `z` stays molecular
(apparent components), exactly the current doctrine.

## Files
- Create: `src/ngdesign/amine/package.py` — `AmineReactivePackage(Thermo)` parameterised by
  the speciation model (`kent_eisenberg` | `enrtl`) and a *carrier* package (the cubic EOS
  for the vapour and for non-electrolyte liquid behaviour). Phase model:
  - **Vapour**: carrier EOS (fugacities, H, S, ρ, μ) — unchanged.
  - **Aqueous liquid** (amine + water + dissolved CO2/H2S + physically dissolved HC):
    - acid gases: fugacity from the speciation model's equilibrium partial pressure,
      `f_i = p_eq,i(loading, T, amine molarity) · φ_i^V(p_eq)`; K_i derived from it.
    - amine, water: Raoult with the carrier's pure Psat (amine vapour pressure from the
      databank; water IAPWS via `pure_psat`), activity 1 in v1 (document; e-NRTL activities
      are a Phase 5 upgrade).
    - hydrocarbons: Henry's law in water, `H_i(T)` from `chemicals` (cite the table used;
      salting-out ignored, documented).
    - **Enthalpy**: carrier liquid H **plus** the heat of absorption:
      ΔH_abs,i(α, T) = −R · ∂ln p_eq,i / ∂(1/T) at constant loading (Gibbs–Helmholtz on the
      speciation model's own equilibrium; cite Kim & Svendsen 2007, Ind. Eng. Chem. Res. 46,
      5803 for the method and the MEA validation band ~80–85 kJ/mol CO2 at low loading,
      MDEA ~50–60 kJ/mol). Evaluated numerically (central difference in 1/T, ΔT = 0.5 K).
    - Cp: numerical dH/dT of the above.
  - PT flash: Rachford–Rice on apparent components with the K-values above, where the
    acid-gas K depends on the liquid loading (inner fixed point on loading, tolerance 1e-8,
    cap 50 iterations). Single-phase detection by the usual bounds. PH/PS: secant on T through
    PT. TVF/PVF, bubble/dew: per P1-01 (bracketed secant).
  - `phase_props`, `k_values`, `derivatives`, `pure_psat`: per the v2 protocol.
- Create: `src/ngdesign/thermo/amine_ke.py` → `@register("thermo", "amine_ke")`,
  `src/ngdesign/thermo/amine_enrtl.py` → `@register("thermo", "amine_enrtl")`, each a
  thin registration of `AmineReactivePackage` with the carrier `pr`.
- Edit: `src/ngdesign/units/mdea_absorber.py`, `mdea_regenerator.py` — when the flowsheet's
  thermo is an amine package, use it for every outlet state (no separate equilibrium call);
  when it is a plain cubic, keep today's behaviour (so existing flowsheets are byte-identical).
  Report heat of absorption in `UnitResult.info["heat_of_absorption_W"]` when available.
- Tests:
  - `tests/thermo/test_amine_package.py`: (1) protocol conformance; (2) 50 wt% MDEA at 313 K,
    loading 0.10 and 0.40 → p_CO2 within 5 % of the NeqSim anchors already carried in
    `kent_eisenberg.py` (0.0093 / 0.229 bara); (3) ΔH_abs for 30 wt% MEA at 313 K, α = 0.2,
    within 80–100 kJ/mol CO2 (Kim & Svendsen Fig. 3 band); MDEA α = 0.2 within 45–65 kJ/mol;
    (4) PT flash of a rich-amine stream with 1 mol% C1 gives a vapour phase whose CO2 partial
    pressure equals `p_eq` within 1e-6 relative; (5) Σβ_k H_k = H identity; (6) H2S rejected
    by `amine_enrtl` with the same typed error e-NRTL raises today.
  - `tests/units/test_amine_units_package.py`: `amine_loop` and `mea_amine_loop` sample
    flowsheets solved with `thermo="amine_ke"` converge; rich-amine duty differs from the
    cubic-only solve by an amount equal to flow × ΔH_abs within 5 % (that *is* the fix).
  - Existing amine unit tests PASS unchanged (plain-cubic path).

## Method
All equations with sources in docstrings. Henry constants and amine Psat from the databank
with provenance. The speciation models are not modified (P0-02 moved them; this spec wraps
them). SI throughout. No tolerance in an existing test changes.

## Acceptance criteria
- [ ] `registry.available("thermo")` includes `amine_ke`, `amine_enrtl`; both pass the v2 protocol test
- [ ] All tests above PASS; `tests/e2e/test_slice.py` byte-identical; golden thermo unchanged
- [ ] `bench/baseline.json --check` passes (amine cases updated with `--update`, numbers stated in the PR)
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green
- [ ] Nothing outside the listed packages changed

## Out of scope
Staged absorber/regenerator (P1-06 after P1-03), e-NRTL activity coefficients on amine/water
(Phase 5), kinetics, degradation products, electrolyte transport properties.
