# multi_stream R1, R2: common-wall layer model (given hA per stream), then plate-fin zoned rating with phase change

- **Family / package:** heat, `src/ngdesign/units/heat/`
- **Levels delivered:** R1, then R2 built on R1; both from catalogue `planned` to `provisional` (`end_state` on R2).
- **Depends on:**
  - the U-R2 conventions and U-01d (#243);
  - R1: nothing else, so it is **parallel-safe now**;
  - R2: **T-PP** (`phase_props` transport properties) and **double_pipe R1 merged** (it imports `rating.film_props`/`inlet_kind`).
- **Wave/order:** R1 parallel-safe; R2 after double_pipe.
- **Branch:** `u-lv/multi_stream` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/heat/multi_stream_r1.py` (new; `MultiStreamR1` plus the common-wall BVP);
  - `src/ngdesign/units/heat/multi_stream_r2.py` (new; `MultiStreamR2` plus plate-fin correlations);
  - `tests/units/heat/test_multi_stream_r1.py`, `tests/units/heat/test_multi_stream_r2.py` (new);
  - `data/validation_units/heat/cases/multi_stream.yaml` (new);
  - the `levels.R1`/`levels.R2` entries of row `multi_stream` in `data/unit_models/heat.yaml`, plus the row `notes`.
  - `units/heat/multi_stream.py` (R0) and `_physics/heat_balance.py` are NOT edited.
- **Read-only imports (verified):**
  - `scipy.integrate.solve_bvp(fun, bc, x, y, tol=..., max_nodes=...)`
  - `scipy.interpolate.PchipInterpolator`
  - `ngdesign.units._physics.heat_balance.TemperatureCross`, `multi_stream`, `MultiStreamSide` (identity test only)
  - `Thermo.flash_ph`, `flash_pt`
  - R2: `ngdesign.units.heat.rating`: `film_props`, `inlet_kind`, `PropertyUnavailable`, `RatingConvergenceError`
  - R2: `ht.Shah(m, x, D, rhol, mul, kl, Cpl, P, Pc)` (condensation), `ht.Liu_Winterton(m, x, D, rhol, rhog, mul, kl, Cpl, MW, P, Pc, Te)` (boiling)
- **Current state:**
  - R0 is `ngdesign.units.heat.multi_stream:MultiStreamExchanger`.
  - Ports `hot_in_1`, `hot_in_2`, `cold_in_1`, `cold_in_2` → positional `hot_out_1/2`, `cold_out_1/2`. Zero-flow ports are allowed and pass through.
  - R0 takes T_out specs on all active streams but one balance stream.
  - info: `duty_<port>_W`, `min_approach_K`, `pinch_T_hot_K`, `pinch_T_cold_K`.

## Method

### Equations (R1, rating)
Common-wall-temperature model: Haseler 1983, "Performance calculation methods for multi-stream plate-fin heat exchangers", in *Heat Exchangers: Theory and Practice*, Hemisphere; Paffenholz 1984. The exchanger's length is normalised, x ∈ [0, 1].
- Each active stream i has a given layer conductance (hA)_i in W/K, the param `hA_<port>_W_K`, distributed uniformly along x.
- Hot streams enter at x = 0 and flow in +x; cold streams enter at x = 1 and flow in −x.
- **Wall temperature** (lateral conduction is perfect and the wall holds no net heat): T_w(x) = Σ_i (hA)_i·T_i(x) / Σ_i (hA)_i.
- **Stream energy balance** in the enthalpy state H_i (W) = F_i·h_i(T_i):
  - hot: dH_i/dx = −(hA)_i·(T_i − T_w);
  - cold: dH_i/dx = +(hA)_i·(T_i − T_w), because its flow direction is −x.
- T_i(H_i) comes from a monotone table per stream: 40 `flash_ph` samples spanning that stream's inlet enthalpy to the enthalpy at the farthest opposite-stream inlet temperature (`flash_pt`). It is interpolated with `PchipInterpolator`, which is monotone and handles phase-change plateaus.
- **Boundary conditions:** H_hot(0) = F·h_in,hot and H_cold(1) = F·h_in,cold.
- **Two-stream reduction:** with constant C, this model is exactly counterflow with 1/UA = 1/(hA)_h + 1/(hA)_c. Verified independently: hA 4000/4000, C 1500/2500, 400/300 K gives Q = 95681.934 W, which equals ε-NTU.

### Algorithm (R1)
1. Collect the active streams (molar flow > 0). Zero-flow ports pass through as copies, as in R0.
   - At least one hot and one cold active stream are required.
   - Hot or cold is the port's role (`hot_in_*`/`cold_in_*`), not a temperature comparison.
2. Build each stream's T(H) table, then solve the BVP with `solve_bvp`, starting from a linear profile between the inlets on a 41-node mesh, with `tol=1e-8` and `max_nodes=20000`.
   - If `sol.status != 0`, raise `RatingConvergenceError` with `sol.message`.
3. Outlets: H at the opposite end, then `flash_ph(z, P_in − dP_<port>, H/F, F)`. The per-stream `dP_<port>` comes from params (default 0), as in R0.
4. **Check:** T_hot(x) ≥ T_w(x) ≥ T_cold(x) on the solution mesh, within −1e-9 K. A violation raises `TemperatureCross` with x and the temperatures; it cannot happen physically, so it signals a table or solver defect.
5. Compute the minimum composite approach and pinch with the same zoned definition as R0: re-run R0's `_pinch`-equivalent check through the public `multi_stream` path in the identity test only. In the adapter, report min_k(T_hot,k − T_cold,k) over the solution mesh as `min_approach_K`.
6. `UnitResult.duty_W` = Σ out − Σ in (round-off), `power_W` = 0. info: per-port duties (R0 sign conventions and key names), `UA_total_W_K` (= Σ over the mesh of the wall-mediated conductance), `min_approach_K`, `bvp_nodes`.

### Equations (R2, zoned plate-fin with phase change)
Each stream i gets a layer geometry (offset-strip fins) instead of hA:
- `n_layers_<port>`, `layer_width_m`, `length_m`;
- fin height h_f, fin spacing s, fin thickness t and strip length l;
- `k_fin_W_mK` (default 180, aluminium alloy).

1. **Per-layer geometry** (Manglik & Bergles 1995, Exp. Therm. Fluid Sci. 10:171):
   - D_h = 4·s·h_f·l / [2(s·l + h_f·l + t·h_f) + t·s];
   - α = s/h_f, δ = t/l, γ = t/s;
   - free-flow area per layer A_ff = (s·h_f)·n_channels, with n_channels = layer_width/(s + t);
   - heat-transfer area per layer A_ht = 2(s + h_f)·L·n_channels (fin plus parting sheet; Shah & Sekulić, *Fundamentals of Heat Exchanger Design*, 2003, §8.2).
2. **Single phase:** j = 0.6522·Re^−0.5403·α^−0.1541·δ^0.1499·γ^−0.0678·[1 + 5.269e-5·Re^1.340·α^0.504·δ^0.456·γ^−1.055]^0.1, and h = j·G·cp·Pr^−⅔ (Manglik & Bergles 1995, eq. 34).
3. **Fin efficiency:** η_f = tanh(mL_f)/(mL_f), with m = √(2h/(k_f·t)) and L_f = h_f/2 for a fin between two parting sheets of the same stream. The surface efficiency is η_o = 1 − (A_fin/A_ht)(1 − η_f) (Shah & Sekulić §4.3), with A_fin/A_ht = h_f/(s + h_f).
4. **Two phase (zone-mean quality 0 < x < 1):**
   - condensing streams: `ht.Shah`;
   - boiling streams: `ht.Liu_Winterton`, with T_e from the R1 wall temperature of that zone;
   - both use D = D_h and the per-channel mass flux. This applies tube correlations to plate-fin channels via D_h, a stated approximation (Shah 1979; Liu & Winterton 1991). The docstring must say so.
5. **Zone procedure:**
   - (a) solve R1 with hA_i from the inlet-state single-phase h;
   - (b) cut the hot composite into `n_zones` equal-ΔH zones (default 20);
   - (c) in each zone, recompute every stream's h at the zone-mean state (single or two phase), giving hA_i,k = h_i,k·η_o,i,k·A_ht,i·(zone length fraction);
   - (d) re-solve the BVP with piecewise-constant hA_i(x) on the zone mesh;
   - (e) repeat (b)–(d) until max |ΔT_out| < 1e-6 K. Cap 30 iterations, else `RatingConvergenceError`.

### Reduction to the lower level
- **R1 → R0:** pass every R1 outlet T except one balance stream as R0 `T_out_<port>` specs, plus the same dP. R0 reproduces all four outlets: the specified ones exactly, and the balance stream's T to 1e-6 K, at the BVP tolerance.
- **R2 → R1:** one zone, all streams single phase, with hA_i set to R2's own zone conductances. R2's outlets equal R1's (run with those hA) to 1e-8 relative.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| no active hot or no active cold stream | `MultiStreamRatingError(ValueError)` (in `multi_stream_r1.py`) | "at least one hot and one cold" |
| an active stream without `hA_<port>_W_K` (R1) or without layer geometry (R2) | `MultiStreamRatingError` | the param name |
| hA ≤ 0 or geometry ≤ 0 | `MultiStreamRatingError` | the param name |
| dP leaving P ≤ 0 | `MultiStreamRatingError` | "non-positive outlet pressure" |
| the hottest cold inlet ≥ the coldest hot inlet with no positive driving force anywhere | `TemperatureCross` | "inlet temperatures" |
| BVP status ≠ 0 or the zone loop does not converge | `RatingConvergenceError` | "did not converge" |
| missing transport properties (R2) | `PropertyUnavailable` | the property |

## Params
R1:
| Name | Type | Unit | Required/default | Meaning |
|---|---|---|---|---|
| `hA_hot_in_1_W_K`, `hA_hot_in_2_W_K`, `hA_cold_in_1_W_K`, `hA_cold_in_2_W_K` | number | W/K | required for each active port | layer conductance of that stream |
| `dP_hot_in_1`, … `dP_cold_in_2` | number | Pa | 0 | per-stream pressure drop |

R2: drop the hA keys and use, per active port, `n_layers_<port>` (int), `fin_height_<port>_m`, `fin_spacing_<port>_m`, `fin_thickness_<port>_m`, `strip_length_<port>_m`; shared `layer_width_m`, `length_m`, `k_fin_W_mK` (180), `n_zones` (20).

```yaml
# R1
type: object
properties:
  hA_hot_in_1_W_K: {type: number, description: 'layer conductance of hot_in_1, W/K'}
  hA_hot_in_2_W_K: {type: number, description: 'layer conductance of hot_in_2, W/K'}
  hA_cold_in_1_W_K: {type: number, description: 'layer conductance of cold_in_1, W/K'}
  hA_cold_in_2_W_K: {type: number, description: 'layer conductance of cold_in_2, W/K'}
  dP_hot_in_1: {type: number, description: 'pressure drop, Pa, default 0'}
  dP_hot_in_2: {type: number, description: 'pressure drop, Pa, default 0'}
  dP_cold_in_1: {type: number, description: 'pressure drop, Pa, default 0'}
  dP_cold_in_2: {type: number, description: 'pressure drop, Pa, default 0'}
```
The R2 YAML lists the geometry keys above with the same description style.

## Outputs
- **Ports:** the four positional outlets.
- **`duty_W`:** round-off residual. **`power_W`:** 0.
- **info:** `duty_<port>_W` (R0 signs), `min_approach_K`, `UA_total_W_K`, `bvp_nodes`. R2 adds `n_zones`, `zone_iterations` and `h_<port>_min_W_m2K`/`h_<port>_max_W_m2K`.

## Tests
- **Closed-form R1**, using the BVP core with a test-only constant-C enthalpy table (T = H/C + T_ref). Independent numbers from `calc_multi_stream.py` (own RK4 plus shooting):
  1. **MS1:** one hot (C 1500 W/K, hA 4000, 400 K) and one cold (C 2500, hA 4000, 300 K). Expect hot out 336.212044 K, cold out 338.272774 K, Q = 95681.934 W, equal to counterflow ε-NTU with UA = 2000 (rel 1e-7).
  2. **MS2:** hot1 (C 1000, hA 3000, 400 K), hot2 (C 800, hA 2000, 380 K), cold (C 2500, hA 5000, 300 K).
     - Expect hot1 out 332.809133 K, hot2 out 334.749305 K, cold out 341.356569 K.
     - Duties Qh1 = 67190.8674 W, Qh2 = 36200.5559 W, Qc = 103391.423 W.
     - Tolerance: abs 1e-5 K on T.
- **Identity:** R1 → R0 and R2 → R1 as above, on `example_case` (the R0 example feeds plus hA values).
- **R2 closed form** (independent numbers from `calc_multi_stream.py`, rel 1e-8):
  - Manglik–Bergles at α 0.5, δ 0.1, γ 0.05:
    - Re 1000: j = 0.0174026135, f_Fanning = 0.108645137;
    - Re 5000: j = 0.00883863219, f = 0.0670128063.
  - Geometry s 1.5 mm, h_f 6.35 mm, t 0.15 mm, l 3.175 mm: D_h = 0.00232730508 m.
  - Fin efficiency at h 500 W/m²K, k_f 180, t 0.15 mm, h_f 6.35 mm: m = 192.45009 1/m, η_f = 0.891694218, η_o = 0.91238959.
- **Refusals:** one per table row.
- **V1 candidates:**
  - R1: there is no open printed multi-stream rating example with printed outlets known to this spec, so record a V1 gap: "searched Haseler 1983, Shah & Sekulić 2003 Ch. 8/9 examples, ALPEMA standards (no worked rating)".
  - R2: no printed plate-fin rating example is known to this spec with confidence. Search Shah & Sekulić 2003 Ch. 9 (plate-fin surface examples) and Kays & London, *Compact Heat Exchangers*, 3rd ed., worked examples. If none prints inputs and outlet results, record the gap with that search list. Never invent numbers.

## Steps
1. The R1 BVP core (pure: tables in, outlet H out) with the constant-C test tables; closed-form MS1/MS2. Push.
2. The `MultiStreamR1` adapter: flash tables, zero-flow pass-through, dP, the wall-ordering check, info, `example_case`; the R1→R0 identity and refusals. YAML `levels.R1` and the harness. Push. **This is the R1 review point.**
3. *(After double_pipe merges.)* R2 pure functions: plate-fin geometry, Manglik–Bergles j, fin and surface efficiency, two-phase calls. Push.
4. The `MultiStreamR2` adapter: the zone loop with piecewise hA(x), the R2→R1 identity and refusals; YAML `levels.R2` and the harness. Push and request review.

## Review checklist
- The flow-direction signs in the BVP are right (cold dH/dx = +hA(T − T_w)). MS1 reproduces ε-NTU.
- The T(H) tables are monotone (PCHIP) and cover the full reachable span. Zero-flow ports pass through untouched.
- Port roles define hot and cold. dP is applied as in R0.
- R2's Manglik–Bergles constants match the 1995 paper. The two-phase tube-correlation-via-D_h approximation is stated in the docstring.
- The R0 module and `heat_balance.py` are untouched.
