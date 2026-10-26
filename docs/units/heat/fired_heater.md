# Fired heater (`fired_heater`)

Family: **heat** · P&ID symbol: `FH`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | process feed (coil inlet) |
| outlet | `outlet` | yes | coil outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.heat.fired_heater:FiredHeater` | process duty from a T_out/duty_W spec; fuel demand from the mixture LHV with water as vapour |
| R1 | provisional | `ngdesign.units.heat.fired_heater_r1:FiredHeaterR1` | radiant/convective split (Lobo-Evans) with the fuel and flue-gas balance solved; bridgewall, stack and crossover temperatures reported |

### R0 parameters

```yaml
properties:
  T_out:
    description: outlet temperature spec, K (one of T_out/duty_W)
    type: number
  dP:
    description: coil pressure drop, Pa
    type: number
  duty_W:
    description: duty spec, W (one of T_out/duty_W)
    type: number
  efficiency:
    description: firing efficiency on the LHV basis, (0, 1]
    type: number
  fuel_composition:
    description: fuel component-id map; fuel flow is the solved demand
    type: object
type: object
```

### R1 parameters

```yaml
properties:
  T_out:
    description: outlet temperature spec, K (one of T_out/duty_W)
    type: number
  UA_convection_W_K:
    description: convection-section UA, W/K
    type: number
  air_T_K:
    description: combustion air temperature, K, default 298.15
    type: number
  air_composition:
    description: air mole fractions, default N2 0.79 / O2 0.21
    type: object
  alpha_Acp_m2:
    description: Lobo-Evans alpha*A_cp, m2
    type: number
  box_P_Pa:
    description: firebox pressure, Pa, default 101325
    type: number
  dP:
    description: coil pressure drop, Pa
    type: number
  duty_W:
    description: duty spec, W (one of T_out/duty_W)
    type: number
  excess_air_frac:
    description: excess air fraction over stoichiometric
    type: number
  exchange_factor:
    description: Lobo-Evans overall exchange factor, (0, 1]
    type: number
  fuel_composition:
    description: fuel component-id map; required at R1
    type: object
  h_conv_radiant_W_m2K:
    description: radiant-section convection, W/(m2 K), default 11.3565267
    type: number
  radiant_loss_frac:
    description: setting loss fraction of fired heat, default 0
    type: number
  tube_area_radiant_m2:
    description: radiant tube outside area, m2
    type: number
  tube_wall_excess_K:
    description: tube wall above mean radiant process T, K
    type: number
required:
- fuel_composition
- excess_air_frac
- alpha_Acp_m2
- exchange_factor
- tube_area_radiant_m2
- tube_wall_excess_K
- UA_convection_W_K
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V2083` | R0 | `info.fuel_LHV_J_per_mol` | 802125 | 802584 | rel 0.001 | pass |

- `V2083`: NBSIR 82-2401, Heating Values of Natural Gas and Its Components (Table 14: methane net heat of combustion 802.125 kJ/mol at 288.15 K and 101.325 kPa). The package's formation-enthalpy LHV (water as VAPOUR, gas-phase standard states at 298.15 K) is 802.584 kJ/mol, +0.057% on the printed value - a reference-state difference, not a calculation choice.

## References

- docs/unit-catalogue-plan.md §2 U-C 7

> V2083 checks the methane LHV against NBSIR 82-2401 (802.125 kJ/mol at 288.15 K; package 802.584 kJ/mol on the 298.15 K formation basis, +0.057%). R1 has no V1 case — Kern Example 19.1 (Process Heat Transfer, 1950, Ch. 19) fixes the 75 % LHV efficiency as a design input and sizes only the radiant section, while R1 rates the efficiency from UA_convection_W_K, which the example does not print, so a case asserting the solved efficiency against 0.75 would echo an input. Kern 1950 Ch. 19, Wimpress 1963 and API 560 were searched for a printed-inputs to printed-outputs fired-heater case without success; any future case id must follow V1-... . The radiant-section solve is kept as a documented comparison test against Kern Example 19.1 in tests/units/heat/test_fired_heater_r1.py (fuel composition, coil fluid and convection UA there are documented carriers).
