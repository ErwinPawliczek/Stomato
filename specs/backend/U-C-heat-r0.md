# U-C: Heat-transfer units, R0

- **Phase:** Unit catalogue round 1. Read `specs/backend/U-R1-round1-conventions.md` first.
- **Depends on:** U-00, U-01
- **Packages you may edit:**
  - `src/ngdesign/units/heat/` (new);
  - `src/ngdesign/units/_physics/heat_balance.py` (new; you own it);
  - `data/unit_models/heat.yaml`, `data/validation_units/heat/`;
  - `tests/units/heat/`, generated `docs/units*`.
- **GitHub issue:** #208
- **Contract change:** no
- **Benchmark delta expected:** none. `heater`, `cooler`, `shell_tube` and `air_cooler` (the single-sided
  `HeatExchanger`) stay untouched.

## Shared physics first: `_physics/heat_balance.py`
- `two_stream(hot, cold, spec, thermo, dP_hot, dP_cold)`, counter-current, where `spec` is exactly one of:
  - `duty_W`;
  - `hot_T_out`;
  - `cold_T_out`;
  - `min_approach_K`, solved by bisection on duty against the zoned check below.
- **Zoned temperature check.** Each side's enthalpy curve is sampled at ≥ 20 points by PH flashes, so
  phase change is seen. The pinch (minimum internal ΔT) is reported, and a spec that produces a
  temperature cross is refused (`TemperatureCross`, naming the ΔT and where it occurs).
- Info: `duty_W`, `LMTD_K` (via `sizing.lmtd_counter` on terminal temperatures, which is only meaningful
  without phase change, so flag `lmtd_valid`), `min_approach_K`, `UA_W_K = duty / LMTD`.
- `multi_stream(hots, colds, specs, thermo)`: each stream has an outlet-T spec except one designated
  balance stream, whose outlet closes the energy balance. The hot and cold composite curves are built
  from the zoned samples, and info gives the minimum approach and pinch temperature. A cross is refused.
- `problem_table(streams, dT_min)`: the Linnhoff problem-table algorithm giving `QH_min`, `QC_min` and
  the pinch temperature. It is for `hen_block` and is pure arithmetic on stream data.

## Units (all R0, `units/heat/`)
| id | R0 method | V1 oracle candidates |
|---|---|---|
| plate_exchanger | `two_stream`; ports hot_in, cold_in, hot_out, cold_out | Kakaç & Liu *Heat Exchangers* duty example; Perry Sect. 11 |
| double_pipe | `two_stream`, same ports | Kern *Process Heat Transfer* Ex. 6.1 (duty and terminal temperatures only at R0) |
| multi_stream | `multi_stream`; N hot and N cold ports declared in the row; the declared optional ports may be zero-flow | Smith *Chemical Process Design* composite-curve example |
| fired_heater | process side heated to `T_out` or `duty_W` by a PH flash; `efficiency` (LHV basis) gives the fuel firing `Q_fired = duty/eff`; with `fuel_composition`, the fuel LHV comes from `ngdesign.data.formation` (`formation_enthalpy_298` of fuel and combustion products, water as vapour), giving the fuel molar rate in info. `duty_W` is the process heat; the flue gas is not modelled at R0 (documented) | GPSA Sect. 8 fired-heater example; LHV of methane 802.3 kJ/mol as a closed-form check |
| cooling_tower | water in and air in, water out and air out. Water outlet T = `T_wet_bulb(air_in) + approach_K`. The wet bulb is solved from the adiabatic-saturation balance using `thermo.pure_psat("H2O", T)`. Evaporation follows from the energy balance (air leaves saturated at a T solved from that balance); `cycles_of_concentration` gives blowdown = evaporation/(COC − 1) and makeup in info | Perry Sect. 12 cooling-tower example; ASHRAE psychrometric chart wet bulb |
| hen_block | analysis unit: N hot and N cold inlets with target outlet T in params; outlets at their targets via PT flash; `duty_W` = net; info from `problem_table` (QH_min, QC_min, pinch) | Linnhoff *User Guide on Process Integration* four-stream example (QH_min, QC_min, pinch exact) |

The electric heater (plan U-C 9) is covered by `heater`, and there is no separate row; note this in the
PR body.

## Out of scope
R1 rating (U from film coefficients) and TEMA geometry; flue-gas composition and the radiant split;
Merkel number.
