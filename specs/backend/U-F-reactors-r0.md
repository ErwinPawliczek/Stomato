# U-F: Reactors, R0 (conversion, yield, equilibrium, Gibbs, electrolyser)

- **Phase:** Unit catalogue round 1. Read `specs/backend/U-R1-round1-conventions.md` first.
- **Depends on:** U-00, U-R (`contracts/reactions.py`, `units/_physics/kinetics.py`), U-01
  (`balance: mass_elements`)
- **Packages you may edit:**
  - `src/ngdesign/units/reactors/` (new);
  - `src/ngdesign/units/_physics/kinetics.py` (additions only; existing functions byte-identical);
  - `src/ngdesign/units/_physics/gibbs.py` (new);
  - `data/unit_models/reactors.yaml` (R0 levels only), `data/validation_units/reactors/`;
  - `tests/units/reactors/`, generated `docs/units*`;
  - `ngdesign.solver`: only the reaction-set resolution hook below.
- **GitHub issue:** #211
- **Contract change:** no. The reaction contract is U-R's and is used as is.
- **Benchmark delta expected:** none

## Reaction-set access (ruling)
`params["reaction_set"]` is one of:
- (a) an inline `ReactionSet` payload (dict), validated with `ReactionSet.model_validate`, used by
  `example_case` and V1 cases; or
- (b) a string id. One hook in `ngdesign.solver` resolves it, before the unit solves, against the
  flowsheet's `Flowsheet.reactions`, and replaces the id with the payload.

An unknown id is refused, naming the ids available. Flowsheets without reactors are byte-identical.

## Step 1: yield-shift core (separate small PR, first)
Add `kinetics.yield_shift(n_in, feed_cids, yields_mass, products)`, a mass-basis lumped shift:
- the feed components are consumed, and the products are formed with the given mass yields (Σ = 1);
- outlet moles come from each product's MW (`component_record`, pseudo-components included);
- yields not summing to 1 within 1e-9 are refused.

Include a closed-form test. Open it as `U-F1: yield-shift core` and comment the link at once: U-H2's
refinery reactors depend on it.

## Units (all R0, `units/reactors/`, every row `balance: mass_elements`)
Thermal modes on every reactor: `adiabatic` (duty 0), `isothermal` (outlet T = inlet T), `duty_W`, or
`T_out`.
- Energy closes on the formation basis via `kinetics.enthalpy_with_formation`: the duty is solved from
  it, or the adiabatic outlet T is found by bisection on it.
- Outlets come from `thermo.flash_pt` on the reacted composition.

| id | R0 method | V1 oracle |
|---|---|---|
| conversion_reactor | sequential or simultaneous fractional conversion per reaction of its `base_component`, via `apply_extents`; refuse a conversion that drives any species negative (naming it) | Fogler (5th ed.) adiabatic conversion example (heat of reaction, outlet T) |
| yield_reactor | `yield_shift` on the declared feed components; element balance checked when every species has a formula, mass balance otherwise | closed-form; any published yield example |
| equilibrium_reactor | extents solving `ln K(T_eq) = Σν ln a_i` for every reaction (ideal-gas activities `y_i·P/P°` at R0, documented), with `T_eq = T_out − approach_K` (approach to equilibrium); Newton on extents with step limiting to keep species ≥ 0; `ln_keq` from kinetics | water-gas shift at 1000 K against the JANAF-based K already measured in U-R (CO conversion closed form); Smith–Van Ness–Abbott Example 13.x |
| gibbs_reactor | `_physics/gibbs.py`: minimise `G = Σ n_i(μ°_i(T) + RT ln(y_i P/P°))` subject to element conservation, by the RAND method (Smith & Missen) or `scipy.optimize` SLSQP with an analytic gradient; params `species` (the product slate), `inerts`, optional `restricted` (fixed extents); ideal gas at R0; `μ°` from `data.formation.formation_gibbs` | steam–methane reforming equilibrium at 1000 K / 1 bar, H2O:CH4 = 2 (Smith–Van Ness–Abbott example, mole fractions to 3 decimals); also gibbs_reactor = equilibrium_reactor on WGS within 1e-6 (V2) |
| electrolyser_stack | water to H2 + O2: params `current_A`, `n_cells`, `cell_voltage_V`, `faradaic_efficiency`; H2 rate `η_F·I·N/(2F)`; `power_W = V·I·N`; outlets `h2_out` and `o2_out` at the stack T and P; the energy balance closes on the formation basis with power as the work input and the remainder as duty (heat rejected) | closed form (Faraday's law; thermoneutral voltage 1.481 V at 298 K as a check on the formation data) |

CSTR and PFR (R1), batch, and fixed-bed multi-tubular rows are not in this round.

## Out of scope
Kinetics-driven reactors; non-ideal activities in the equilibrium and Gibbs reactors (R0 is ideal gas,
documented); catalyst models.
