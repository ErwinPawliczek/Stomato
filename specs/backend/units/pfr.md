# pfr R1, R2, R3: kinetic plug-flow reactor (extents ODE; Ergun and wall heat transfer; effectiveness and deactivation)

- **Family / package:** reactors, `src/ngdesign/units/reactors/`
- **Levels delivered:** R1, R2 and R3 of row `pfr`, each from `planned` to `provisional`. Three PRs in order: R1, then R2 after R1 merges, then R3 after R2 merges.
- **Depends on:** U-R2 conventions, U-01d (#243). U-R (#199, merged) for `ReactionSet` and `_physics.kinetics`.
- **Wave/order:** **first in the reactor chain.** pfr R1 owns the shared plug-flow integrator. `naphtha_ht` R1 and `reformer_cat` R1 start once pfr R1 has merged; `fixed_bed_tubular` R2 starts once pfr R2 has merged. `cstr` runs in parallel with all of it.
- **Branch:** `u-lv/pfr` (R1), `u-lv/pfr-r2` (R2), `u-lv/pfr-r3` (R3) · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/reactors/plug_flow.py` (new): the shared integrator, a public API other units import.
  - `src/ngdesign/units/reactors/pfr.py` (new): adapters `PfrR1`, `PfrR2`, `PfrR3`.
  - `tests/units/reactors/test_pfr_r1.py`, `test_pfr_r2.py`, `test_pfr_r3.py` (new).
  - `data/validation_units/reactors/cases/pfr.yaml` (new).
  - The `levels.R1`, `levels.R2` and `levels.R3` entries of row `pfr` in `data/unit_models/reactors.yaml`, plus that row's `balance: mass_elements` key (the row lacks it today; add it in the R1 PR) and its `notes` line.
- **Read-only imports (verified to exist):**
  - `ngdesign.units._physics.kinetics.rate(reaction: Reaction, T: float, P: float, z: Mapping[str, float]) -> float`
  - `ngdesign.units._physics.kinetics.heat_of_reaction(reaction: Reaction, T: float) -> float` (J per mol extent, ideal-gas formation basis)
  - `ngdesign.units._physics.kinetics.apply_extents(n_in, rset, extents) -> dict[str, float]`, which raises `ReactionExtentError` on negative amounts
  - `ngdesign.units._physics.kinetics.enthalpy_with_formation(state: StreamState) -> float` (W)
  - `ngdesign.units._physics.kinetics.R` (8.31446261815324) and `KineticsError`
  - `ngdesign.units.reactors._shared.reaction_set_param(value) -> ReactionSet`, `thermal_outlet(inlet, n_out, thermal, thermo, *, power_W=0.0) -> (StreamState, duty_W)`, `z_from(n) -> dict`, and `_solve_outlet_T(thermo, z, total, P, T_in, target_W) -> float`. This last one is private but is the single owner of the T-from-formation-enthalpy root. Import it read-only, and do not copy it.
  - `scipy.integrate.solve_ivp(fun, t_span, y0, method=..., rtol=..., atol=..., events=...)` (scipy 1.18.1)
  - `Thermo.flash_pt(z, T, P, molar_flow) -> StreamState`; `StreamState.component_flows()`; `Phase.cp` (J/(mol·K)), `Phase.density` (kg/m³), `Phase.viscosity` (Pa·s or None), `Phase.molecular_weight` (g/mol)
- **Current state:** the row has only `planned` levels; there is no adapter. No unit calls `kinetics.rate` yet, so this is its first consumer.

## Method

### Equations
Index `i` runs over components and `j` over reactions. V is reactor volume (m³) and F the molar flows (mol/s).

1. **Species flows from extents:** F_i(V) = F_i,0 + Σ_j ν_ij·ξ_j(V). This is `apply_extents` arithmetic, and it is the definition of an extent.
2. **Extent ODE** (Fogler, *Elements of CRE*, mole-balance design equation dF_A/dV = r_A, written per reaction):
   dξ_j/dV = s_j · a · η_j · r_j(T, P_eff, z) / |ν_base,j|.
   - r_j = `kinetics.rate(...)` is the rate of disappearance of reaction j's base component, in the reaction's `rate_units`. That is the contract's base-component extent basis.
   - Dividing by |ν_base,j| turns the base-component consumption rate into an extent rate. With ν_base = −1, as in all of Fogler's examples, the two coincide.
   - In R1 and R2, a = η_j = 1. In R3 they are given by equations 9–10.
3. **Rate-basis scale s_j**, from `reaction.kinetics.rate_units`:
   - `"mol/(m3·s)"`, `"mol/(m3*s)"` or `"mol/m3/s"` give s_j = 1;
   - `"mol/(kg_cat·s)"`, `"mol/(kg_cat*s)"` or `"mol/kg_cat/s"` give s_j = ρ_b, the param `bulk_density_kg_m3`;
   - any other string is refused.
4. **Concentration-equivalent pressure.** `kinetics.rate` builds concentrations as c_i = y_i·P/(R·T); this is the contract's definition.
   - **Vapour reacting phase:** P_eff = P, the contract's ideal-gas definition, used unchanged.
   - **Liquid reacting phase:** P_eff = c_tot·R·T with c_tot = 1000·ρ/MW (mol/m³, from the liquid `Phase.density` and `Phase.molecular_weight`). `rate` then sees c_i = x_i·c_tot exactly. This needs no contract change.
   - Mole-fraction-basis rates do not depend on P_eff.
5. **Energy ODE** (adiabatic, uniform-duty and coolant modes; Fogler ch. 11, steady-state PFR energy balance):
   dT/dV = [ −Σ_j ΔH_j(T)·dξ_j/dV + q_V ] / ( Σ_i F_i · c_p,mix ).
   - ΔH_j(T) = `heat_of_reaction(reaction_j, T)`.
   - c_p,mix is the single phase's `Phase.cp` from `flash_pt(z, T, P, F_tot)`.
   - q_V is the heat added per unit volume (W/m³): 0 when adiabatic, Q/V_total for uniform duty, and equation 7 in R2.
6. **Accumulated heat:** dQ/dV = q_V, with Q(0) = 0.
7. **R2 wall heat transfer** to a coolant at fixed temperature (Fogler ch. 11): q_V = U·a_w·(T_c − T), with a_w = 4/D_t (m²/m³) for a circular tube.
8. **R2 Ergun pressure drop.** Fogler eq. 4-22 in SI, divided by the cross-section to make it per unit volume:
   dP/dV = −(1/A_c) · G(1−φ)/(ρ·D_p·φ³) · [150(1−φ)μ/D_p + 1.75·G].
   - A_c = π·D_t²/4 is the cross-section per tube.
   - G = ṁ/(n_t·A_c) is the superficial mass flux, constant along the tube.
   - ρ and μ come from the flash at (z, T, P); μ can be overridden by the param `viscosity_Pa_s`.
   - Without a `bed` param, dP/dV = 0 (an empty tube carries no pressure drop at R2).
9. **R3 generalized Thiele modulus and effectiveness.** Aris's shape-normalized form (Fogler ch. 15; Froment, Bischoff & De Wilde ch. 3), for a power-law reaction of order n in its base component:
   - φ_j = L_p · sqrt( ((n+1)/2) · r_p,j / (D_e · C_s,j) );
   - L_p = R_p/3 for a sphere;
   - r_p,j = s_j·r_j/(1−ε_b) is the rate per pellet volume;
   - C_s,j is the base-component bulk concentration: y_base·P_eff/(R·T), or for a liquid x·c_tot;
   - η_j = tanh(φ_j)/φ_j, and η_j = 1 − φ_j²/3 when φ_j < 1e-4.
10. **R3 activity**, a power-law decay da/dt = −k_d·a^m evaluated at time on stream t (separable, uniform along the bed; Fogler ch. 10):
    a = [1 + (m−1)·k_d·t]^{1/(1−m)} for m ≠ 1, and a = exp(−k_d·t) for m = 1. The steady-state equivalent is the bed frozen at activity a(t).

### Algorithm
`plug_flow.integrate_plug_flow` is the public API, owned by this spec. `naphtha_ht`, `reformer_cat` and `fixed_bed_tubular` import it.

```python
class PlugFlowError(ValueError): ...

@dataclass(frozen=True)
class HeatModel:                       # R2: pluggable wall heat transfer
    n_extra: int                       # extra ODE states (0 for fixed coolant T)
    y0_extra: tuple[float, ...]
    q_V: Callable[[float, float, Sequence[float]], float]           # (V, T, extra) -> W/m3 into process
    d_extra: Callable[[float, float, Sequence[float]], Sequence[float]]  # (V, T, extra) -> d(extra)/dV

@dataclass(frozen=True)
class PlugFlowProfile:
    V_m3: tuple[float, ...]; T_K: tuple[float, ...]; P_Pa: tuple[float, ...]
    extents: tuple[tuple[float, ...], ...]     # per output point, per reaction
    extra: tuple[tuple[float, ...], ...]
    Q_W: float; n_rhs: int

def integrate_plug_flow(
    inlet: StreamState, rset: ReactionSet, thermo: Thermo, *,
    volume_m3: float,
    energy: Literal["isothermal", "adiabatic", "uniform_duty", "heat_model"],
    duty_W: float = 0.0, heat: HeatModel | None = None,
    reacting_phase: Literal["vapor", "liquid"] = "vapor",
    bulk_density_kg_m3: float | None = None,
    ergun: ErgunBed | None = None,             # R2; None = no pressure drop
    rate_multiplier: Callable[[int, float, float, Mapping[str, float]], float] | None = None,  # R3: (j, T, P, z) -> a*eta_j
    n_output: int = 51,
) -> PlugFlowProfile
```

Steps:
1. **Initial state.** y = [ξ_1..ξ_m, T, P, Q, extra…], starting from y0 = [0…, T_in, P_in, 0, y0_extra…]. In isothermal mode T is held: dT/dV = 0, and dQ/dV is set by the outlet closure, not integrated.
2. **RHS.**
   - Compute F from ξ (equation 1). If any F_i < 0, raise `PlugFlowError` naming the component and V.
   - Flash z = F/ΣF with `flash_pt(z, T, P, ΣF)`.
   - Refuse two-phase states: a vapour fraction strictly between 1e-9 and 1 − 1e-9 raises `PlugFlowError`, because the PFR is single-phase.
   - Get P_eff (equation 4), the rates (equations 2–3), q_V, dT/dV (equation 5), dP/dV (equation 8, or 0) and d(extra)/dV.
   - Count RHS calls; at **20,000** raise `PlugFlowError("RHS evaluation cap")`.
3. **Integration.** `solve_ivp(rhs, (0, volume_m3), y0, method="BDF", rtol=1e-8, atol=atol, t_eval=linspace(0, V, n_output), events=[depletion, pressure_floor])`.
   - atol = [1e-12·F_tot,0 for each ξ; 1e-8 K for T; 1e-6 Pa for P; 1e-8·max(1, |duty|) for Q; 1e-8 for each extra].
   - `depletion` is terminal: min_i F_i − 1e-14·F_tot,0 crossing zero. Raise `PlugFlowError` naming the component and V: a zero-order rate has depleted a reactant.
   - `pressure_floor` is terminal: P − 0.1·P_in. Raise `PlugFlowError("pressure drop exceeds 90 % of inlet pressure at V = …")`.
   - `sol.success` False raises `PlugFlowError` with `sol.message`.
4. **Outlet** (adapters). n_out = `apply_extents(inlet.component_flows(), rset, ξ(V_end))`. The energy balance is then closed exactly on the formation basis. **The closure, not the ODE, owns T_out.**
   - R1 isothermal: `thermal_outlet(inlet, n_out, "isothermal", thermo)`.
   - R1 adiabatic: `thermal_outlet(inlet, n_out, "adiabatic", thermo)`.
   - R1 uniform duty: `thermal_outlet(inlet, n_out, {"duty_W": q}, thermo)`.
   - R2 (outlet at P_out = P(V_end) ≠ P_in):
     - isothermal: `flash_pt(z_from(n_out), T_in, P_out, Σn)`, with duty = enthalpy_with_formation(out) − enthalpy_with_formation(inlet);
     - adiabatic or coolant: T_out = `_solve_outlet_T(thermo, z_from(n_out), Σn, P_out, T_in, enthalpy_with_formation(inlet) + Q)`, with duty = Q.
5. **Info.**
   - `extent_<id>_mol_s` per reaction;
   - `T_profile_out_K` (the ODE's end temperature) and `T_closure_gap_K` = T_out − T_profile_out_K;
   - `T_max_K` and `V_at_T_max_m3`;
   - `P_out_Pa` and `dP_Pa` (R2);
   - `n_rhs`;
   - R3: `activity` and `eta_<id>_inlet`.

   The gap comes from the ideal-gas ΔH in equation 5 against the package's residual enthalpy. It is reported, never forced to zero.

### Reduction to the lower level
- **R2 → R1:** with `energy="adiabatic"` (no coolant), no `bed`, and volume = n_t·A_c·L equal to R1's `volume_m3`, the R2 outlet equals R1's to 1e-10 relative (same integrator path, P constant).
- **R3 → R2:** with `deactivation` absent (a = 1) and `effectiveness` given as 1.0 for every reaction (η = 1), the R3 outlet equals R2's to 1e-12. The multiplier is exactly 1.0.
- **R1:** this is the row's first level, with no R0. Its identity test instead requires that with every k0 = 0 the outlet equals the inlet re-flashed at (T_in, P_in), with duty 0 to 1e-9 W.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| `volume_m3` ≤ 0 (R1), or `length_m`/`tube_diameter_m`/`n_tubes` ≤ 0 (R2) | `PlugFlowError` | the parameter name |
| `rate_units` not in the accepted lists | `PlugFlowError` | `reaction '<id>': rate_units` |
| a catalyst-mass rate without `bulk_density_kg_m3` | `PlugFlowError` | `bulk_density_kg_m3` |
| an LHHW reaction that also carries an `equilibrium` model (LHHW ignores it). A PowerLaw with `equilibrium` and no `reverse` is VALID: since #245 `kinetics.rate` applies forward·(1 − Q/K). | `PlugFlowError` | `LHHW` |
| reaction without kinetics (`kinetics is None`) | `PlugFlowError` | `has no kinetics` |
| two-phase state, or a negative species, along the reactor | `PlugFlowError` | `two-phase` / `depletes` |
| RHS cap reached, or `solve_ivp` failure | `PlugFlowError` | `RHS evaluation cap` / `integration failed` |
| R2: viscosity unavailable (`Phase.viscosity is None`) and no `viscosity_Pa_s` | `PlugFlowError` | `viscosity_Pa_s` |
| R2: `bed.voidage` not in (0, 1), or `particle_diameter_m` ≤ 0 | `PlugFlowError` | the field name |
| R2: P falls below 0.1·P_in | `PlugFlowError` | `pressure drop exceeds` |
| R3: `effectiveness` missing for a reaction that is not a single-base-order power law (LHHW, or one with a reverse) | `PlugFlowError` | `effectiveness` |
| R3: `deactivation.order` < 0, or `k_d_per_s`/`time_on_stream_s` < 0 | `PlugFlowError` | the field name |

## Params
**R1**

| name | type | unit | required/default | range | meaning |
|---|---|---|---|---|---|
| reaction_set | object/str | — | required | — | inline ReactionSet (string ids are resolved by the solver) |
| volume_m3 | number | m³ | required | > 0 | reactor volume |
| thermal | str/object | — | `"isothermal"` | `"isothermal"`, `"adiabatic"`, `{"duty_W": W}` | energy mode; duty spread uniformly over V |
| reacting_phase | str | — | `"vapor"` | `"vapor"`, `"liquid"` | single phase the flow must stay in |
| bulk_density_kg_m3 | number | kg/m³ | required if any rate is per kg_cat | > 0 | catalyst bulk density |

**R2** adds the following and replaces `volume_m3`:

| name | type | unit | required/default | range | meaning |
|---|---|---|---|---|---|
| tube_diameter_m | number | m | required | > 0 | tube inside diameter |
| length_m | number | m | required | > 0 | tube length |
| n_tubes | integer | — | 1 | ≥ 1 | parallel identical tubes |
| thermal | — | — | — | — | R1's modes plus `{"coolant_T_K": K, "U_W_m2K": W/m²K}` (fixed coolant temperature) |
| bed | object | — | absent | — | `{"particle_diameter_m": m, "voidage": (0,1)}`; present → Ergun |
| viscosity_Pa_s | number | Pa·s | from the flash | > 0 | Ergun viscosity override |

**R3** adds:

| name | type | unit | required/default | range | meaning |
|---|---|---|---|---|---|
| pellet | object | — | absent | — | `{"radius_m": m, "effective_diffusivity_m2_s": m²/s}` (sphere); requires `bed.voidage` |
| effectiveness | object | — | absent | each in (0, 1] | `{reaction_id: η}`, which overrides the Thiele modulus |
| deactivation | object | — | absent | — | `{"order": m ≥ 0, "k_d_per_s": ≥ 0, "time_on_stream_s": ≥ 0}` |

JSON-schema fragment for R1 (R2 and R3 extend it the same way):
```yaml
params:
  type: object
  required: [reaction_set, volume_m3]
  properties:
    reaction_set: {description: inline ReactionSet, or a string id resolved against Flowsheet.reactions}
    volume_m3: {type: number, description: reactor volume, m3}
    thermal: {description: "'isothermal' | 'adiabatic' | {duty_W: W} (uniform along V); default isothermal"}
    reacting_phase: {type: string, enum: [vapor, liquid], description: single phase the flow must stay in; default vapor}
    bulk_density_kg_m3: {type: number, description: catalyst bulk density, kg/m3; required for per-kg_cat rates}
```

## Outputs
- Port `outlet`: the flash from the exact energy closure (algorithm step 4).
- `duty_W`: heat added to the process; isothermal and coolant modes carry the reaction heat. `power_W` is 0.
- The row declares `balance: mass_elements`, so V0 closes mass, elements and formation-basis energy at 1e-8.
- `info`: as in algorithm step 5. Units are in the key names.

## Tests
- **Closed-form, R1-A** (isothermal first order; `calc_pfr.py`):
  - Case: nC4 → iC4 (base nC4, ν = −1), PowerLaw with k0 = 1.0e3 s⁻¹, Ea = 5.0e4 J/mol, order 1 in nC4, basis `concentration`, `rate_units` `"mol/(m3·s)"`.
  - Feed: pure nC4, 1.0 mol/s at 500 K and 2.0e5 Pa; V = 2.0 m³; isothermal.
  - Hand calculation: Da = k·(P/RT)·V/F0, and X = 1 − exp(−Da), exact because Δn = 0.
  - Values: k = 5.97912989e-3 s⁻¹, c = 48.108942 mol/m³, Da = 0.575299226, **X = 0.437463482**, F_nC4 = 0.562536518, F_iC4 = 0.437463482 mol/s.
  - Tolerance: 1e-7 relative (rtol 1e-8). Run it on `pr`; the rate uses the contract's ideal concentration, so the package does not matter.
- **Closed-form, R2-a** (Ergun, inert):
  - Case: N2 at 0.1 mol/s, 300 K, P0 = 2.0e5 Pa; thermo `ideal-raoult` (exact ideal-gas density); `viscosity_Pa_s` 1.8e-5; empty reaction set; isothermal.
  - Geometry: D_t 0.05 m, L 5.0 m, n_t 1; bed D_p 0.003 m, φ 0.4.
  - Fogler eq. 4-33: P/P0 = sqrt(1 − 2β0L/P0). A_c = 1.96349541e-3 m², G = 1.42671075 kg/(m²·s), ρ0 = 2.24615839 kg/m³, β0 = 6027.72916 Pa/m.
  - Result: **P_out = 167166.21 Pa** (ΔP = 32833.7903 Pa). Tolerance 1e-6 relative.
- **Closed-form, R2-b** (wall heat transfer, inert):
  - Case: N2 at 0.1 mol/s, T0 = 305 K, 2.0e5 Pa, `ideal-raoult`; coolant 300 K, U = 5 W/(m²·K), same tube; no bed.
  - With c_p = 29.2132106 J/(mol·K) (the package's N2 c_p at 302.5 K): T_out = T_c + (T0 − T_c)·exp(−U·a_w·V/(F·c_p)), with U·a_w·V = 3.92699082 W/K.
  - Result: **T_out = 301.303674 K** and Q = −10.7981558 W. Tolerance 2e-4 K; c_p changes by less than 0.01 % over 300–305 K.
- **Closed-form, R3** (`calc_pfr.py`):
  - Case: the R1-A reaction with Ea = 0 and k0 = 9.6 s⁻¹ (per reactor volume); feed 1.0 mol/s, 500 K, 2.0e5 Pa; V = 1.0e-3 m³; isothermal.
  - Pellet: R_p = 1.5e-3 m, D_e = 1.0e-6 m²/s; bed voidage 0.4. Deactivation: order 2, k_d 1.0e-6 s⁻¹, t = 2.592e5 s.
  - Intermediate values: k_p = 16 s⁻¹, φ = 2, η = 0.48201379, a = 0.794155019, Da = 0.461845843.
  - Result: **X = 0.162045659**, against X = 0.36988053 with η = a = 1. Tolerance 1e-7 relative.
- **Identity:** R2 → R1 and R3 → R2 as stated, plus R1 with all k0 = 0.
- **Adiabatic consistency (R1):**
  - Case: exothermic dimerisation 2 C2H4 → 1-butene on `ideal-raoult`, adiabatic. V0 closes at 1e-8.
  - Requirements: `abs(T_closure_gap_K)` < 1e-3 K (an ideal-gas package makes equation 5 and the closure consistent), and T_out > T_in.
  - If `ideal-raoult` lacks property data for C2H4 or 1-butene, use nC4 → iC4 instead (ΔH ≈ −8 kJ/mol). Say which in the test docstring.
- **Refusals:** one test per row of the refusal table, each `pytest.raises(PlugFlowError, match=...)` on an input that reaches that check.
  - For the zero-order depletion case, use a zero-order reaction with a long V.
  - For two-phase, use a feed that condenses along an isothermal cooled R2.
- **V1 candidates** (cite only after confirming the printed page):
  - Fogler, *Elements of Chemical Reaction Engineering*, 4th ed., ch. 4: the full-scale tubular ethane-cracking-to-ethylene PFR example (isothermal, first order). It prints the inputs and the volume for X = 0.8.
  - The same chapter's packed-bed pressure-drop example (Ergun with reaction).
  - **Confirm the example numbers and every printed value from the book itself.** If the book is not accessible, ship with the V1 gap recorded in the row `notes`, naming the searches.

## Steps (each about 40 minutes, each ending in a push)
1. **R1 core.** `plug_flow.py`: `PlugFlowError`, the extents ODE (equations 1–4), isothermal mode, the RHS cap, the depletion event and `PlugFlowProfile`. Test R1-A at the integrator level.
2. **R1 energy.** Adiabatic and uniform-duty modes (equations 5–6). Adapter `PfrR1` in `pfr.py` with the step 4 closure via `thermal_outlet`, and `example_case` (the R1-A feed). The adiabatic consistency test, the k0 = 0 identity and the R1 refusals.
3. **R1 catalogue.** YAML `levels.R1` (+ `balance: mass_elements`), `cases/pfr.yaml` (V1 or gap), harness write and `--audit`, CI green. Open the R1 PR (title `pfr R1: kinetic plug-flow reactor`).
4. **R2 pressure** (new branch after R1 merges). `ErgunBed`, the P state and equation 8 in `plug_flow.py`; tube geometry params; `PfrR2` with the step 4 R2 closure. Tests R2-a and R2 → R1 identity.
5. **R2 heat.** `HeatModel` (equation 7, fixed coolant T) and the coolant thermal mode. Test R2-b, the R2 refusals, YAML `levels.R2`, cases and docs. Open the R2 PR.
6. **R3** (after R2 merges). `rate_multiplier` hook use: equations 9–10, the `pellet`/`effectiveness`/`deactivation` params, `PfrR3`. Tests R3 and R3 → R2 identity, the refusals, YAML `levels.R3` (`end_state` stays on R3). Open the R3 PR.

## Review checklist (for the orchestrator)
- The extent rate divides by |ν_base| (equation 2), and the rate-units scale follows equation 3 exactly.
- P_eff = P for vapour and c_tot·R·T for liquid; no other use of P_eff.
- The outlet T comes from `thermal_outlet` / `_solve_outlet_T`, never from the ODE. `T_closure_gap_K` is reported, not hidden.
- BDF with rtol 1e-8 and the stated atol vector; RHS cap 20,000; the events are terminal and typed.
- No equilibrium-without-reverse refusal (#245 fixed `kinetics.rate` to forward·(1 − Q/K)); a test reaches Q/K → 1 at the outlet; LHHW + equilibrium is refused.
- The `HeatModel` and `rate_multiplier` hooks are public and documented, so fixed_bed, naphtha_ht and reformer need not edit `plug_flow.py`.
- Ergun in SI with no g_c; a_w = 4/D_t; G is per tube.
- R3's η uses tanh(φ)/φ with L_p = R_p/3, and the order-m activity formula.
- Identity tests are at 1e-10 / 1e-12, and every refusal is reached.
