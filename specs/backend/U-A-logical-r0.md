# U-A: Logical and stream-handling units, R0

- **Phase:** Unit catalogue round 1. Read `specs/backend/U-R1-round1-conventions.md` first; it binds this spec.
- **Depends on:** U-00, U-01
- **Packages you may edit:**
  - `src/ngdesign/units/logical/` (new);
  - `src/ngdesign/units/_physics/splitting.py` (new; you own it);
  - `data/unit_models/logical.yaml`, `data/validation_units/logical/`;
  - `tests/units/logical/`, generated `docs/units*`;
  - `ngdesign.solver`: only the lowering hook in step 4.
- **GitHub issue:** #206
- **Contract change:** no
- **Benchmark delta expected:** none

## Goal
Complete the logical family so a canvas can express component splits, stream arithmetic, balance closure,
explicit recycles, adjusts and utility accounting.

## Step 1: shared split helper (separate small PR, first)
Create `units/_physics/splitting.py` with:

    split_by_component(state, fractions, thermo, outlet_T, outlet_P) -> (top, bottom)

- `fractions` maps cid to the fraction sent to the first outlet. Components missing from it go to the
  second outlet.
- Each outlet is flashed at its own `(outlet_T, outlet_P)`, which default to the inlet's T and P. The
  returned duty is `ΣnH out − ΣnH in`.
- Include a closed-form test.
- Open this as its own PR, `U-A1: splitting helper`, and comment its link on the issue at once. U-D
  (hydrocyclone, filter, membrane) waits on it.
- Then continue on the family branch.

## Units (all R0, `units/logical/`)
| id | R0 method |
|---|---|
| component_splitter | `splitting.split_by_component`; params `fractions`, optional outlet T/P per port; duty reported |
| stream_calculator | one inlet, one outlet: `scale` (multiply flow), `set` overrides of T, P or flow, then a PT flash; any composition override renormalised and refused when negative; duty = enthalpy change |
| stream_duplicator | N outlets (`n_copies`, default 2), each an identical copy. **This breaks mole balance by design.** Rule: copies are reference streams: outlet `copy_0` carries the material and copies `1..N−1` carry the same intensive state with `molar_flow` scaled by `params.copy_flow_scale` (default 0.0, so the balance closes). The full-flow mirror form is refused at R0 unless `allow_unbalanced: true`, which V0 never uses. Document this |
| balance | closes one unknown outlet: inlets minus the declared `known_outlets` (given as FeedSpec kwargs in params), per component, then a PH flash at a given P, so the energy closes as well. Refuse negative component flows, naming the component |
| recycle_block | pass-through identity at R0, with params `tolerance` and `acceleration ∈ {none, wegstein, broyden}`; see step 4 |
| adjust | pass-through identity at R0, with params `{target: {stream, variable, value}, manipulate: {unit, param}, bounds}`; see step 4 |
| utility_stream | metering pass-through: one inlet, one outlet; params `kind ∈ {steam_lp, steam_mp, steam_hp, cooling_water, fuel_gas, electricity, refrigerant}` and `price` (currency per unit basis); info `utility_cost_rate`. Cost is a pass-through number, not physics |

## Step 4: solver lowering (the only solver edit allowed)
`adjust` and `recycle_block` become declarative nodes. Add one lowering function in `ngdesign.solver` that
runs before the solve:
- `adjust` nodes become the existing P2-01 `DesignSpec`;
- `recycle_block` nodes mark the existing P2-03 tear stream and set its acceleration options.

Both nodes stay identity units in the graph. Flowsheets without these nodes are byte-identical (bench
`--check`). Add one e2e test per node, solving a small flowsheet that a P2-01 / P2-03 test already
solves, and show both forms give the same answer within 1e-8.

## V1
Logical units have no textbook worked example. A closed-form test per unit replaces V1, and the gap is
recorded in each row's notes ("closed-form only; definitional unit").

## Out of scope
Utility pricing data; cost estimation; any new acceleration method.
