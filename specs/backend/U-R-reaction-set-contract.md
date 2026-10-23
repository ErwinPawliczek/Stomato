# U-R: Reaction-set contract — stoichiometry, kinetics forms, formation properties, extent arithmetic

- **Phase:** Unit catalogue, round 0 (docs/unit-catalogue-plan.md §3, §5)
- **Depends on:** none (P1-07 flowsheet-owned pseudo pattern on main)
- **Packages you may edit:** `ngdesign.contracts` (new `reactions.py`; `flowsheet.py`: `Flowsheet.reactions`), `ngdesign.data` (new `formation.py`), `ngdesign.units._physics` (new package: `__init__.py`, `kinetics.py`), `tests/contracts/`, `tests/data/`, `tests/units/physics/`, `openapi.json` + `frontend/src/api/schema.d.ts` (regenerated only)
- **Contract change:** yes — new reaction-set models and `Flowsheet.reactions` (orchestrator applies `contract-change`)
- **Benchmark delta expected:** none (no unit uses it yet)
- **GitHub issue:** #192

## Goal
One owner for reaction chemistry before any reactor exists. Every reactor in rounds 1–3 (conversion,
yield, equilibrium, Gibbs, CSTR, PFR, refinery lumped reactors) names a flowsheet-owned reaction set
and calls this module; no reactor carries stoichiometry, a rate law or a heat of reaction of its own.

## Files
- Create `contracts/reactions.py` (pydantic, frozen, JSON-round-trippable like the rest of `contracts`):
  - `Reaction`: `id`, `stoichiometry: dict[str, float]` (component id → ν, reactants negative), `phase: "V"|"L"|"overall"`, `base_component` (must have ν < 0), `kinetics: Kinetics | None`, `equilibrium: Equilibrium | None`, `provenance: str` (required, non-empty).
  - `Kinetics` (discriminated union on `form`): `PowerLaw` (k0, Ea [J/mol], T_ref optional, orders per component, basis `"concentration"|"partial_pressure"|"mole_fraction"`), `LHHW` (driving force terms + adsorption group with exponent, each with its own Arrhenius pair), `Reversible` (forward PowerLaw + reverse either PowerLaw or `from_equilibrium`). Rate units declared on the model (`mol/(m3·s)` or `mol/(kg_cat·s)`), never implied.
  - `Equilibrium`: `form: "from_gibbs"|"lnK_polynomial"`; polynomial `lnK = A + B/T + C ln T + D T` with validity window `T_K`; basis as in `Kinetics`.
  - `ReactionSet`: `id`, `reactions: list[Reaction]`, `components: list[str]`.
  - Validators: element balance of every reaction ≤ 1e-9 relative for databank species (formula from `ngdesign.data`); pseudo-components allowed only in reactions flagged `lumped: true` (mass balance checked instead of elements); duplicate ids, unknown components and ν = 0 entries refused with typed errors.
- Edit `contracts/flowsheet.py`: `Flowsheet.reactions: list[ReactionSet] = []`. A flowsheet without reactions serialises byte-identically (exclude-default, the P1-07 pattern); goldens unchanged.
- Create `data/formation.py`: `formation_properties(cid) -> FormationProps(Hf_ig_298, Gf_ig_298, S_ig_298, source)` from the `chemicals` databank (`chemicals.reaction.Hfg`, `Gfgs`, `S0g`) with the source string returned; pseudo-components and species without data raise `MissingFormationData` naming the component. No hand-typed tables.
- Create `units/_physics/__init__.py` (empty docstring module; future families add their own stores here) and `units/_physics/kinetics.py`:
  - `stoich_matrix(rset, slate)`; `apply_extents(n_in, rset, extents) -> n_out` refusing negative outlets with the offending component;
  - `rate(reaction, T, P, phase_state) -> mol/(m3·s)` for each kinetics form;
  - `ln_keq(reaction, T)`: `from_gibbs` integrates van't Hoff with ideal-gas Cp from the databank (ΔG°(298) and ΔH°(T) via ∫ΔCp dT, cite the textbook form, e.g. Smith–Van Ness–Abbott ch. 13), `lnK_polynomial` evaluates the polynomial and refuses outside its window;
  - `heat_of_reaction(reaction, T)` = Σν(Hf_ig,298 + ∫Cp_ig dT), ideal-gas basis, documented.
  - `enthalpy_with_formation(thermo, state) -> J/s`: the package's stream enthalpy plus Σ n_i Hf_i,298 — the single function every reactor energy balance uses. Before it is trusted, measure each package's enthalpy reference: for every catalogue package with an `example` feed, H of each pure component as ideal gas at 298.15 K / 101325 Pa (or the package's documented reference). Record the measured offsets in the module docstring; a package whose reference is not the ideal-gas-298 basis gets its offset applied here (one place), never in a reactor.

## Method — tests (named, all PASS)
- `tests/contracts/test_reactions.py`: round-trip JSON; element-balance refusal (`CH4 + O2 → CO2 + H2O` with wrong ν refused, balanced accepted); pseudo in a non-lumped reaction refused; flowsheet without reactions byte-identical to main's JSON.
- `tests/data/test_formation.py`: Hf/Gf of CH4, CO2, H2O(g), NH3 match the databank values and the source string is non-empty; a pseudo raises `MissingFormationData`.
- `tests/units/physics/test_kinetics.py`:
  - water–gas shift `ln K` at 500, 700, 900 K from `from_gibbs` vs a cited published value (e.g. Moe 1962 / Twigg Catalyst Handbook correlation `log10 K = 2073/T − 2.029`) within 2 % in K;
  - ammonia synthesis ΔH_r(298) = −45.9 kJ/mol NH3 ±0.3 (NIST-JANAF via the databank);
  - a closed-form check: isothermal first-order A→B power-law rate equals `k0·exp(−Ea/RT)·C_A` to 1e-12;
  - `apply_extents` mass conserved to 1e-12 and negative-outlet refusal;
  - `enthalpy_with_formation` on the reaction products minus reactants at 298.15 K ideal-gas equals `heat_of_reaction` to 1e-6 relative, with PR, SRK and one gamma-phi package (this is the reference-offset test).
- Every constant in a test cites its source in a comment; no test asserts a value computed by the code under test.

## Acceptance criteria
- [ ] Contract models validate, round-trip and refuse as specified; openapi/schema regenerated, frontend `check:api`/`typecheck` green
- [ ] Package enthalpy reference offsets measured and recorded; `enthalpy_with_formation` test green on three packages
- [ ] All named tests pass; ruff, ruff format, `mypy src tests`, lint-imports green; bench counts byte-identical; goldens unchanged
- [ ] Nothing outside the listed packages changed

## Out of scope
Any reactor unit; Gibbs minimisation (round 1, U-F, built on `kinetics.py`); catalyst deactivation; reactive column stages; electrolytes in reactions.
