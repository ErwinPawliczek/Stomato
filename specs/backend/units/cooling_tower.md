# cooling_tower R1: Merkel number (Chebyshev 4-point) against a tower characteristic; water outlet solved, then the R0 balance

- **Family / package:** heat, `src/ngdesign/units/heat/`
- **Levels delivered:** R1, from catalogue `planned` to `provisional` (`end_state: true` stays on R1).
- **Depends on:** the U-R2 conventions and U-01d (#243). No transport properties are needed. **Parallel-safe now.**
- **Branch:** `u-lv/cooling_tower` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/heat/cooling_tower_r1.py` (new; `CoolingTowerR1` plus pure functions);
  - `tests/units/heat/test_cooling_tower_r1.py` (new);
  - `data/validation_units/heat/cases/cooling_tower.yaml` (new);
  - the `levels.R1` entry of row `cooling_tower` in `data/unit_models/heat.yaml`, plus the row `notes`.
  - `units/heat/cooling_tower.py` (R0) is NOT edited. Import `CoolingTower` and `wet_bulb` from it read-only.
- **Read-only imports (verified):**
  - `ngdesign.units.heat.cooling_tower.CoolingTower` (the R0 adapter: approach-based balance);
  - `ngdesign.units.heat.cooling_tower.wet_bulb(thermo: Thermo, air: StreamState, water_composition: dict[str, float] | None = None) -> float` (public; the adiabatic-saturation wet bulb, K; raises ValueError when no bracket is found);
  - R0 `CoolingTower.solve` reads `params["cycles_of_concentration"]` (default 3.0) and `params["approach_K"]` (required);
  - `Thermo.flash_pt`, `Thermo.pure_psat("H2O", T)`, `Thermo.phase_props`;
  - `scipy.optimize.brentq`.
- **Current state:**
  - R0 is `ngdesign.units.heat.cooling_tower:CoolingTower`.
  - Ports `water_in`, `air_in` → `water_out`, `air_out`.
  - The water outlet is **fixed** at T_wb + `approach_K` (required). The exit air is saturated at the temperature that closes the energy balance. Blowdown and makeup come from `cycles_of_concentration`.
  - V2085 checks the wet bulb against ASHRAE.

## Method

### Equations
1. **Merkel equation** (Merkel 1925; ASHRAE Handbook HVAC Systems and Equipment, Ch. 40; CTI ATC-105):
   KaV/L = ∫ from T_out to T_in of c_pw·dT / (h_s(T) − h_a(T)).
   - h_s is the enthalpy of saturated air at the water temperature, per kg of dry air;
   - h_a is the bulk air enthalpy on the operating line h_a(T) = h_a,in + (L/G)·c_pw·(T − T_out). Merkel's assumptions: evaporation loss neglected in L, and a Lewis factor of 1.
2. **Chebyshev 4-point integration** (CTI ATC-105; ASHRAE HVAC S&E Ch. 40):
   KaV/L ≈ c_pw·(T_in − T_out)/4 · Σ_{i=1..4} 1/Δh_i, with Δh_i = h_s(T_i) − h_a(T_i) at T_i = T_out + f_i·(T_in − T_out), f = (0.1, 0.4, 0.6, 0.9).
3. **Tower characteristic** (CTI): KaV/L = C·(L/G)^(−n), with params C (`characteristic_C`) and n (`characteristic_n`).
4. **Enthalpies, consistent with R0's thermo basis:**
   - per kg of dry air, h(T, y) = [(1 − y)·h_dry(T) + y·h_vap(T)] / [(1 − y)·MW_dry/1000], using the same construction as R0 `_humid_enthalpy` (re-implemented in this module; the R0 helpers are private);
   - y_s(T) = p_sat(T)/P, with p_sat from `thermo.pure_psat("H2O", T)`;
   - h_a,in is the inlet air enthalpy per kg of dry air at its own humidity;
   - c_pw = [h_w(T_in) − h_w(T_out)]/[(T_in − T_out)·MW_w/1000], with h_w from `flash_pt({"H2O": 1}, T, P_water, 1)` (liquid). Only enthalpy differences enter, so the reference state cancels.
   - L = water mass flow (kg/s) and G = dry-air mass flow (kg/s), both from the inlets.

### Algorithm
1. Validate the params and inlets (as R0: both flowing, with water and dry-gas components present). T_wb = `wet_bulb(thermo, air_in, ...)`.
2. Unknown T_out, solved by brentq on (T_wb + 1e-6, T_in − 1e-6) with r(T_out) = KaV/L_Chebyshev(T_out) − C·(L/G)^(−n).
   - As T_out → T_wb, the Merkel integral grows without bound and r > 0. As T_out → T_in, the range shrinks to 0, Merkel → 0 and r < 0.
   - If any Δh_i ≤ 0 at some T_out, the operating line touches saturation: return r = +∞ (treat as an infinite tower).
   - xtol 1e-10 K, maxiter 100, else `CoolingTowerConvergenceError`.
3. approach = T_out − T_wb. **Delegate to R0:** `CoolingTower().solve(inlets, {**params_R0, "approach_K": approach}, thermo)`, passing `cycles_of_concentration` through. All outlets, the energy closure and blowdown/makeup are then R0's by construction.
4. info = R0's info, plus `merkel_KaV_L`, `characteristic_KaV_L`, `L_over_G`, `range_K` and `approach_K` (the solved one).

### Reduction to the lower level
R1's result equals R0's result run with `approach_K` = R1's `info["approach_K"]`, bit for bit (`==` on every outlet field), because R1 delegates to R0.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| `characteristic_C` ≤ 0 or `characteristic_n` < 0 | `CoolingTowerSpecError(ValueError)` | the param name |
| `approach_K` given at R1 (R1 solves it) | `CoolingTowerSpecError` | "approach_K is solved at R1" |
| water inlet at or below the inlet wet bulb | `CoolingTowerSpecError` | "wet bulb" |
| a zero-flow water or air inlet | ValueError, as R0 | as R0 |
| no root in the bracket, or no convergence | `CoolingTowerConvergenceError(ValueError)` | "Merkel" |

## Params
| Name | Type | Unit | Required/default | Range | Meaning |
|---|---|---|---|---|---|
| `characteristic_C` | number | – | required | > 0 | C in KaV/L = C(L/G)^−n |
| `characteristic_n` | number | – | required | ≥ 0 | n in the same |
| `cycles_of_concentration` | number | – | 3 | ≥ 1 | passed to R0 |

```yaml
type: object
required: [characteristic_C, characteristic_n]
properties:
  characteristic_C: {type: number, description: 'tower characteristic coefficient C in KaV/L = C (L/G)^-n'}
  characteristic_n: {type: number, description: 'tower characteristic exponent n'}
  cycles_of_concentration: {type: number, description: 'cycles of concentration, >= 1 (default 3)'}
```

## Outputs
- **Ports:** R0's `water_out` and `air_out`, unchanged.
- **`duty_W` and `power_W`:** R0's.
- **info:** R0's keys plus `merkel_KaV_L`, `characteristic_KaV_L`, `L_over_G`, `range_K`, and `approach_K` (now an output).

## Tests
- **Closed-form** (the pure Chebyshev integrator with an injected h_s callable; independent numbers from `calc_cooling_tower.py`). The test supplies h_s from ASHRAE Fundamentals 2017 SI, Ch. 1:
  - Hyland–Wexler p_ws over liquid (eq. 6): C8 −5.8002206e3, C9 1.3914993, C10 −4.8640239e−2, C11 4.1764768e−5, C12 −1.4452093e−8, C13 6.5459673;
  - W_s = 0.621945·p_ws/(P − p_ws);
  - h = 1.006t + W(2501 + 1.86t) kJ/kg_da.
  1. p_ws(303.15 K) = 4246.03024 Pa (ASHRAE Table 3 prints 4.2467 kPa at 30 °C, consistent); h_s(303.15) = 99.731526 kJ/kg_da.
  2. T_in 313.15 K, T_out 303.15 K, L/G 1.2, c_pw 4.186 kJ/kgK, h_a,in 72.0 kJ/kg_da:
     - Chebyshev points 304.15/307.15/309.15/312.15 K;
     - Δh = 28.0517468, 30.5546328, 33.6545199, 40.7852585;
     - **KaV/L = 1.28310338** (rel 1e-8).
  3. Characteristic C 1.7, n 0.6 at L/G 1.2 gives 1.52384282.
- **Identity:** R1 equals R0 at the solved approach (bitwise), on `example_case`. Use the R0 example feeds with C = 1.7, n = 0.6, and check that the solved approach lies between 1 and 15 K.
- **Monotonicity:** a larger C gives a smaller T_out (strictly), across C ∈ {1.0, 1.7, 2.5}.
- **Refusals:** one per table row.
- **V1 candidates:**
  - ASHRAE Handbook HVAC Systems & Equipment, Ch. 40 (cooling towers), example of a Merkel number by the Chebyshev method. It prints the inputs (temperatures, L/G, wet bulb) and KaV/L.
  - Perry's Chemical Engineers' Handbook, 8th ed., §12 (cooling towers), Example: "Calculation of required tower characteristic". It prints the inputs and the computed KaV/L.
  - **Case construction:** such examples print T_in, T_out, wet bulb, L/G and the resulting KaV/L. At R1, T_out is an output, so the case sets `characteristic_C` = the printed KaV/L, with `characteristic_n` = 0, and the expected quantity is `water_out.T`, the printed cold-water temperature.
    - That is a legitimate printed result: the book derives KaV/L from T_out, and the case runs the inverse.
    - The tolerance is the book's rounding on T, plus the h_s-basis difference, which goes to `assessed` if missed.
  - Never use the printed KaV/L as both input and expected value.
  - If neither source is accessible: "V1 gap: searched ASHRAE HVAC S&E Ch. 40, Perry's 8th §12, Kern 1950 Ch. 17".

## Steps
1. Pure functions: Chebyshev Merkel with injected h_s and h_a; the thermo-based h_s and h_a per kg dry air; c_pw from enthalpies. Closed-form tests 1–3. Push.
2. The adapter: the brentq on T_out, delegation to R0, info, `example_case`; the identity, monotonicity and refusal tests. Push.
3. The YAML `levels.R1`, the V1 case or gap (see the caveat above), harness runs. Push and request review.

## Review checklist
- The Chebyshev points are (0.1, 0.4, 0.6, 0.9) of the range with weight range/4. The operating line uses the dry-air G and L/G from the inlets.
- h_s and h_a are on the same thermo basis, per kg of dry air.
- The residual signs and bracket are as specified, with Δh ≤ 0 handled.
- R1 delegates to R0 for all outlets, so there is no second energy balance. `approach_K` is refused as an input at R1.
- A V1 case never uses an input echo as its expected value.
