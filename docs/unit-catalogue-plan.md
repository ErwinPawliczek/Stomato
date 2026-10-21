# Plan: the unit-operation catalogue (~70 units) built breadth-first, then in rigour rounds

> **Status: draft, not for dispatch.** Agreed in outline on 2026-10-21. The programme is re-evaluated
> with Erwin after the thermo catalogue freeze (T wave 4) and before U-00 is written: scope cuts
> (electrolysers, membranes, adsorption, Claus, cooling towers, hydrocyclones are candidates), the
> reaction contract's placement in U-00, and the exclusion of dynamic mode are the open decisions.
> Nothing in this file is a spec until that review.

Written 2026-10-21, while the thermo catalogue (`docs/thermo-catalogue-plan.md`, 168 property
methods in 8 families) is landing. This plan starts when that catalogue is frozen (its wave 4) and
P1-11/P1-06 have put the amine units on the rigorous column, so the unit layer never competes with
thermo or column threads for files.

## 0. Principles

1. **Breadth first, then rounds.** Round 0 gives every unit in the catalogue a base model (R0)
   that closes balances exactly and solves from a spec. Round 1 lifts every unit to its next
   rigour level (R1), round 2 to R2, and so on. No unit skips a level: R2 is only reachable
   through a green R1, because each level's validation cases become the regression floor for the
   next.
2. **Rigour is a per-unit option, not a new unit.** One registered id per unit (`shell_tube`,
   `pfr`, ...); the level is `params["model"]` (the P1-06 `mode="shortcut"|"staged"` pattern).
   Flowsheets, sizers, the P&ID builder and the agent see one unit whose fidelity can be raised
   without rewiring. A level that is not implemented refuses with a typed error naming the levels
   that are.
3. **Units consume the `Thermo` protocol only.** No unit imports a property package, a flowsheet
   or another unit's internals (the import-linter contracts already enforce this). Every new
   physics the units need from thermo (transport properties, `dlnφ/dn`, reaction enthalpies) is a
   contract change raised against the thermo layer, never a workaround inside a unit.
4. **Units are data in the registry.** `data/unit_models/<family>.yaml` lists every unit: id,
   family, adapter, ports, parameter schema per level, implemented levels with status, validation
   case ids, sizer and P&ID symbol. `ngdesign.units.catalogue` registers from it, exactly as
   `thermo.catalogue` does; the frontend palette, the agent's `build` tool and the docs derive
   from the same file.
5. **Every level is validated against a worked example with a citation before it ships**, and
   every unit at every level closes mass, energy and (where reactions exist) element balances to
   1e-8 relative on its `example_case()` — the locked property test extended per level.
6. **The fix philosophy holds:** one owner per invariant. Pressure drop lives in one correlation
   store (`fluids`), heat-transfer coefficients in one (`ht`), reaction stoichiometry and kinetics
   in one contract (`contracts/reactions.py`), stage equations in one column package. A unit never
   re-derives physics another module owns.

## 1. Rigour levels, defined once

| Level | Meaning | What it needs from the stack |
|---|---|---|
| **R0 base** | balances + a spec: outlet state from a duty, ΔP, split, conversion, efficiency or approach; no sizing physics | `Thermo` flashes only |
| **R1 rating** | performance from geometry and correlations: ΔP from a line, U from film coefficients, stages from Kremser/FUG, conversion from kinetics in an ideal reactor | `fluids`, `ht`, reaction set |
| **R2 rigorous** | the governing equations solved on a discretised domain: MESH stages, PFR integrated along length with heat transfer, TEMA exchanger zones, two-phase pipe profiles | column package, ODE/DAE solvers, transport properties |
| **R3 advanced** | rate-based / non-equilibrium stages, CFD-free but mechanistic internals, catalyst deactivation, dynamic holdup (dynamic mode is a separate axis, out of scope here) | mass-transfer correlations, interfacial area models |

Not every unit has four levels. A mixer is complete at R0; a valve ends at R1; a column and a
reactor go to R3. The catalogue says, per unit, which levels exist and which are the end state.

## 2. Catalogue (71 units)

Status today: ✅ exists at the level shown, 🟡 exists but the level/contract must change, ❌ missing.

### U-A Logical and stream handling (9)

| # | unit | R0 | R1 | R2 | today |
|---|---|---|---|---|---|
| 1 | mixer | pressure = min inlet, adiabatic PH flash | — | — | ✅ R0 |
| 2 | splitter | fractions / flows | — | — | ✅ R0 |
| 3 | component splitter | per-component split fractions, outlet T/P specs | — | — | ❌ |
| 4 | stream calculator (set) | copy/scale/override stream variables | — | — | ❌ (P2-01 design specs exist; the unit form is missing) |
| 5 | adjust | manipulate a unit param to hit a stream target (wraps design specs) | — | — | 🟡 solver-level only |
| 6 | balance | mass/energy balance block closing an unknown stream | — | — | ❌ |
| 7 | recycle block | explicit tear with per-block acceleration options | — | — | 🟡 implicit in solver (P2-03) |
| 8 | stream duplicator / tee | identical copies | — | — | ❌ |
| 9 | utility stream source/sink | steam levels, cooling water, fuel gas, electricity with cost basis | — | — | ❌ |

### U-B Pressure change and flow (12)

| # | unit | R0 | R1 | R2 | today |
|---|---|---|---|---|---|
| 1 | pump | ΔP/outlet P + efficiency, PS flash | curve (head/efficiency vs flow), NPSHa | — | ✅ R0 |
| 2 | centrifugal compressor | isentropic/polytropic efficiency | map (head/efficiency vs flow, surge/stonewall), Schultz polytropic | multi-section with intercooling | ✅ R0; train ✅ |
| 3 | reciprocating compressor | clearance-volume model, stages | rod load, capacity vs clearance | — | ❌ |
| 4 | expander / turbine | isentropic efficiency | map | — | ✅ R0 |
| 5 | JT valve | isenthalpic | — | — | ✅ R0 |
| 6 | control valve | Cv / outlet P, isenthalpic | IEC 60534 sizing, choked flow, Cv curve | — | ❌ (correlation `cv_liquid` exists) |
| 7 | relief valve | set pressure, orifice from API 520 | two-phase (HEM/omega), inlet/outlet loss checks | — | ❌ (correlations `psv_api520_gas` exist) |
| 8 | pipe segment | fixed ΔP | single-phase Darcy (Colebrook), elevation | two-phase Beggs-Brill / `fluids` multiphase, profile along length | ❌ (correlations exist) |
| 9 | orifice / flow element | ΔP from Cd | ISO 5167 | — | ❌ |
| 10 | ejector | entrainment ratio spec | 1-D momentum (ESDU-style) | — | ❌ |
| 11 | fan / blower | ΔP + efficiency | curve | — | ❌ |
| 12 | hydraulic turbine / pressure recovery | isentropic | — | — | ❌ |

### U-C Heat transfer (10)

| # | unit | R0 | R1 | R2 | today |
|---|---|---|---|---|---|
| 1 | heater / cooler | duty or outlet T, ΔP | — | — | ✅ R0 |
| 2 | shell-and-tube exchanger | approach / duty, LMTD-F spec | rating: U from `ht` film coefficients, TEMA type, F factor, ΔP both sides | zoned (phase change), multi-pass with temperature cross | ✅ R0 + sizer |
| 3 | air cooler | approach / duty | rating: bundle geometry, fan power, `ht` air-side | — | ✅ R0 + sizer |
| 4 | plate exchanger | approach / duty | rating: chevron correlations | — | ❌ |
| 5 | double-pipe / hairpin | approach / duty | rating | — | ❌ |
| 6 | multi-stream (LNG cold box) | stream-by-stream duties, composite curves, pinch check | layer-wise UA distribution | zoned with phase change | ❌ |
| 7 | fired heater | duty, efficiency, fuel from LHV | radiant/convective split (Lobo-Evans) | — | ❌ |
| 8 | cooling tower | approach to wet bulb, evaporation + blowdown | Merkel | — | ❌ |
| 9 | electric heater | duty | — | — | ❌ (R0 is the heater) |
| 10 | heat exchanger network block (HEN) | pinch targets from stream data | — | — | ❌ (engineering deliverable, not a solve unit) |

### U-D Phase separation (10)

| # | unit | R0 | R1 | R2 | today |
|---|---|---|---|---|---|
| 1 | 2-phase separator / KO drum | PT/PH/PVF flash, ΔP | Souders-Brown sizing, carry-over at a given diameter | — | ✅ R0 + sizer (scrubber) |
| 2 | 3-phase separator | VLLE flash | sizing, weir/interface levels, residence | — | ✅ R0 + sizer |
| 3 | flash drum with duty | PH/PT flash with duty spec | — | — | 🟡 (separator without duty) |
| 4 | decanter | LLE split | settling (Stokes) | — | ❌ |
| 5 | tank / surge drum | mixing with holdup (steady = mixer) | — | — | ❌ |
| 6 | hydrocyclone / cyclone | efficiency spec | Lapple / Barth cut size | — | ❌ |
| 7 | filter | solids split spec | cake resistance | — | ❌ |
| 8 | membrane (gas) | stage-cut / permeance spec | solution-diffusion with permeances, cross-flow | counter-current module | ❌ |
| 9 | adsorption bed (TSA/PSA) | equilibrium capacity + breakthrough spec | Langmuir isotherm, LUB | — | ❌ |
| 10 | hydrate check / inhibitor injection | hydrate T from Hammerschmidt + inhibitor dose | Katz / van der Waals-Platteeuw (via thermo) | — | ❌ (correlations exist) |

### U-E Columns and staged contactors (12)

| # | unit | R0 | R1 | R2 | R3 | today |
|---|---|---|---|---|---|---|
| 1 | shortcut distillation (FUG) | Fenske-Underwood-Gilliland, Kirkbride feed stage | — | — | — | ❌ |
| 2 | rigorous distillation | — | — | MESH, condenser/reboiler kinds, specs (P1-03) | rate-based stages, Murphree/vaporisation efficiencies | ✅ R2 (two-tear) |
| 3 | absorber (feed-determined) | Kremser | — | MESH zero-tear (P1-09) | rate-based | ✅ R0 (`kremser`) + R2 |
| 4 | reboiled stripper | Kremser | — | MESH one-tear (P1-10) | rate-based | ✅ R2 |
| 5 | refluxed absorber / reboiled absorber | — | — | MESH with one end exchanger | — | 🟡 (configurations exist; tests missing) |
| 6 | side draws, pumparounds, multiple feeds, inter-stage heaters | — | — | MESH extensions | — | 🟡 draws exist; pumparounds ❌ |
| 7 | three-phase (VLLE) stages | — | — | MESH with two liquids per stage | — | ❌ |
| 8 | reactive stages (equilibrium / kinetic) | — | — | MESH + reaction set on stage holdup | — | ❌ (amine chemistry lives in the package, not the stage) |
| 9 | liquid-liquid extractor | stage-count from Kremser | — | MESH with LLE stages | — | ❌ |
| 10 | divided-wall / Petlyuk | — | — | two coupled MESH sections | — | ❌ |
| 11 | column internals (trays/packing) | — | hydraulics: flooding, pressure drop, HETP (Perry/`fluids`) | — | — | ❌ (sizer scope) |
| 12 | batch distillation | — | — | — | dynamic (separate axis) | ❌ |

### U-F Reactors (9)

| # | unit | R0 | R1 | R2 | R3 | today |
|---|---|---|---|---|---|---|
| 1 | conversion reactor | fractional conversion per reaction, heat of reaction, adiabatic/isothermal/duty | — | — | — | ❌ |
| 2 | yield reactor | product yields, element-balance check | — | — | — | ❌ |
| 3 | equilibrium reactor (Keq) | Keq(T) per reaction, approach-to-equilibrium ΔT | — | — | — | ❌ |
| 4 | Gibbs reactor | Gibbs minimisation over a species set, inerts, restricted equilibria | — | — | — | ❌ |
| 5 | CSTR | — | kinetics (Arrhenius, LHHW, power-law), single phase | multi-phase with VLE in the vessel | — | ❌ |
| 6 | PFR | — | kinetics, adiabatic/isothermal | integrated along length with heat transfer, pressure drop (Ergun) | catalyst deactivation, pellet effectiveness | ❌ |
| 7 | batch / semi-batch reactor | — | — | — | dynamic (separate axis) | ❌ |
| 8 | fixed-bed multi-tubular | — | — | PFR with shell-side coolant | — | ❌ |
| 9 | electrolyser / fuel cell stack | conversion + Faradaic efficiency | polarisation curve | — | — | ❌ |

### U-G Gas treating and specialty (9)

| # | unit | R0 | R1 | R2 | today |
|---|---|---|---|---|---|
| 1 | amine absorber (MDEA/DEA/MEA) | single-stage shortcut with Kent-Eisenberg | — | staged on the reactive package (P1-06) | ✅ R0; R2 blocked on P1-11 |
| 2 | amine regenerator | shortcut | — | reboiled stripper on the reactive package (P1-06) | ✅ R0; R2 blocked on P1-11 |
| 3 | TEG contactor | activity-based water spec | — | staged with TEG activity package | ✅ R0 + sizer |
| 4 | TEG regenerator + stripping gas | shortcut | — | staged | ❌ |
| 5 | Claus sulfur recovery (thermal + catalytic stages) | conversion/equilibrium per stage | — | Gibbs per stage | ❌ |
| 6 | molecular sieve dehydration | adsorption bed (U-D 9) with cycle | — | — | ❌ |
| 7 | LNG liquefaction block (C3MR / DMR) | composition of flowsheet units; a template, not a unit | — | — | ❌ (flowsheet template) |
| 8 | NGL fractionation train (deethaniser/depropaniser/debutaniser) | flowsheet template over rigorous columns | — | — | ❌ (template) |
| 9 | sour-water stripper | reboiled stripper on an electrolyte package (T-09) | — | — | ❌ |

## 3. Architecture that makes the catalogue cheap

- **One `UnitModel` protocol, one catalogue.** `contracts/plugins.py::UnitModel` stays as is
  (ports, `solve(inlets, params, thermo)`, `example_case`). `data/unit_models/<family>.yaml`
  (`_schema.yaml` shared) carries id, family, adapter, ports, `levels: {R0: {status, params,
  validation}, R1: ...}`, sizer id, symbol. `ngdesign.units.catalogue` loads and registers, and
  refuses a `params["model"]` level that is not implemented with the list of those that are.
- **Shared physics stores, each with one owner.** `units/_physics/pressure_drop.py` (over
  `fluids`), `units/_physics/heat_transfer.py` (over `ht`), `units/_physics/efficiency.py`
  (polytropic/isentropic, curves), `contracts/reactions.py` + `units/_physics/kinetics.py`
  (stoichiometry, Arrhenius/LHHW/power-law, Keq(T) from ΔG via thermo, Gibbs minimisation). Units
  call these; they never carry a correlation of their own.
- **Reaction sets are flowsheet-owned data**, the P1-07 pattern: `Flowsheet.reactions` holds
  named sets with stoichiometry, kinetics form and parameters with provenance; a reactor unit
  names the set it uses. Heats of reaction come from the thermo package's formation enthalpies
  (contract addition: `Thermo.formation_enthalpy(cid)`), never typed into the reactor.
- **Discretised units share one integrator.** PFR, two-phase pipe and zoned exchangers integrate
  along a coordinate with the same adaptive stepper (`scipy.integrate.solve_ivp` wrapped once in
  `units/_physics/profile.py`), reporting the profile in `info` the way the column reports stages.
- **Templates are flowsheets, not units.** LNG blocks, NGL trains, amine loops are
  `ngdesign.flowsheets` samples that compose catalogue units; they are the L3 canonical cases.
- **Sizers follow the level.** A sizer reads the solved unit's `info` at whatever level it
  solved; an R1 rating fills the datasheet fields an R0 sizer estimated. The P&ID symbol is
  per unit, not per level.

## 4. Validation layers (the gate for a level's `validated`)

| Layer | What | Oracle |
|---|---|---|
| **V0 self-consistency** | mass, energy and element balances ≤ 1e-8 relative on `example_case()` at every implemented level; determinism; port contract; refusal of unimplemented levels with a typed error; sizer runs on the result | mathematics; the locked `tests/property/test_unit_balances.py` extended per level |
| **V1 worked example** | one cited textbook/handbook example per unit per level reproduced within the book's rounding: Perry (separators, exchangers, valves), GPSA (compressors, air coolers, TEG, amine), Seader-Henley (FUG, absorbers, extractors), Fogler/Levenspiel (reactors), Crane TP-410 (pipes/valves), API 520/521 (relief), Kern/`ht` references (exchanger rating) | published numbers with citation |
| **V2 cross-level consistency** | R1 reproduces R0 when given the spec R0 solved to; R2 reproduces R1 inside R1's validity window (e.g. FUG stage count vs MESH at the same reflux ratio within the Gilliland scatter; Kremser vs zero-tear MESH within 2 % — already measured in P1-09) | internal |
| **V3 flowsheet regression** | bench cases and goldens byte-identical for existing units; every new unit appears in one sample flowsheet that the e2e suite solves | existing bench/golden machinery |

Rules: a level ships `provisional` with V0 + V2 green and V1 lacking an open example, `validated`
only with V0–V2 green, `experimental` for levels whose physics is stubbed. The harness
(`scripts/validate_units.py`) writes `docs/units/<id>.md` per unit with the level table and the
worked-example residuals, regenerated in CI like `docs/validation/`.

## 5. Orchestration: rounds of parallel threads, partitioned by family

Partition by file ownership so threads never collide:

| Thread owns | Package / files |
|---|---|
| U-00 catalogue + harness + reaction contract | `units/catalogue.py`, `data/unit_models/_schema.yaml`, `scripts/validate_units.py`, `contracts/reactions.py`, `units/_physics/` skeletons, migration of the 21 existing units into the YAML |
| U-A logical | `units/logical/`, `data/unit_models/logical.yaml` |
| U-B pressure/flow | `units/flow/`, `units/_physics/pressure_drop.py`, `data/unit_models/flow.yaml` |
| U-C heat transfer | `units/heat/`, `units/_physics/heat_transfer.py`, `data/unit_models/heat.yaml` |
| U-D separation | `units/separation/`, `data/unit_models/separation.yaml` |
| U-E columns | `units/column/` (extensions only), `units/shortcut_column.py`, `data/unit_models/column.yaml` |
| U-F reactors | `units/reactors/`, `units/_physics/kinetics.py`, `data/unit_models/reactors.yaml` |
| U-G treating | `units/treating/` (the amine/TEG modules move here), `data/unit_models/treating.yaml`, sample flowsheets |
| U-V validation data per family | `data/validation_units/<family>/cases.yaml`, data-only PRs in parallel with the unit threads |

Rounds (each round = one dispatch burst per family; a family's round N+1 starts when its round N
and U-00 are on main):

1. **Round 0 (serial, 1 thread):** U-00. Catalogue-as-data, level refusal, V0 harness, reaction
   contract, the 21 existing units migrated with their current level recorded. Nothing else starts
   before its schema is merged.
2. **Round 0 breadth (parallel, 7 threads):** U-A..U-G at **R0** for every ❌ unit above, plus
   U-V worked-example data for R0. Target: 71 units registered, each solving its example case with
   balances at 1e-8, each with a V1 example or a documented gap.
3. **Round 1 rating (parallel, 6 threads):** every unit with an R1 column above: curves, Cv,
   Darcy, exchanger rating over `ht`, Souders-Brown, kinetics in ideal reactors, Kremser/FUG,
   membrane permeances. U-A has no R1 and skips.
4. **Round 2 rigorous (parallel, 4 threads):** PFR along length, two-phase pipes, zoned/multi-pass
   exchangers, MESH extensions (pumparounds, VLLE stages, reactive stages, extractor, divided
   wall), Gibbs per Claus stage, staged TEG regenerator.
5. **Round 3 advanced (parallel, 2 threads):** rate-based stages (mass-transfer correlations and
   interfacial area as a shared store), catalyst deactivation and pellet effectiveness.
6. **Freeze:** every level's status audited against its harness report; `docs/units/` regenerated;
   the agent's `build` tool and the frontend palette regenerated from the catalogue.

Orchestrator duties per PR, unchanged: worktree, every gate, bench counts byte-identical for
existing units, the harness report for the units the PR adds, a probe of the V1 example, then
approve and auto-merge. Threads post an hourly checkpoint on their issue; a silent thread is
re-dispatched after three hours.

Budget: U-00 plus 7 + 6 + 4 + 2 family threads and ~7 data sweeps ≈ 27 Obvious threads. Round 0
breadth is the largest burst and is bounded by U-F (reactors need the reaction contract end to
end); each later round is smaller because the shared physics stores already exist.

## 6. Dependencies on the rest of the roadmap

- Starts after the thermo catalogue freeze (T wave 4) and P1-11/P1-06, so columns and thermo are
  stable under the units.
- Contract additions raised against thermo before Round 1: transport properties on `PhaseProps`
  (μ, k, σ are already on the v2 contract; verify every catalogue row fills them or refuses),
  `formation_enthalpy`/`gibbs_formation` for reaction heats and Keq, and `dlnφ/dn` for rate-based
  stages (Round 3).
- Dynamic mode (batch reactors, batch distillation, surge dynamics) is a separate axis and a
  separate plan; this catalogue is steady-state only.
- Engineering deliverables (datasheets, equipment list, line list) extend per level through the
  sizers; they are tracked in the engineering plan, not here.

## 7. Risks

- **Reactors are the biggest new surface.** The reaction contract (U-00) must land clean: a bad
  stoichiometry/kinetics schema would be re-done four times. Review it as a contract change.
- **`ht`/`fluids` coverage is wide but uneven**; every R1 correlation call cites the correlation
  it uses and records its validity window in the row, so a unit refuses outside it rather than
  extrapolating.
- **Rate-based stages (Round 3) are research-grade**; the plan allows `experimental` there and
  does not gate the freeze on them.
- **Breadth can hide depth**: the V2 cross-level check is what keeps R0 honest once R1/R2 exist,
  so it is mandatory from Round 1 on.
