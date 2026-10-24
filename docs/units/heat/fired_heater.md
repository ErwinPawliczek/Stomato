# Fired heater (`fired_heater`)

Family: **heat** · P&ID symbol: `FH`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | process feed (coil inlet) |
| outlet | `outlet` | yes | coil outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.heat.fired_heater:FiredHeater` | process duty from a T_out/duty_W spec; fuel demand from the mixture LHV with water as vapour |
| R1 | planned | — | radiant/convective split (Lobo-Evans) |

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

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V2083` | R0 | `info.fuel_LHV_J_per_mol` | 802125 | 802584 | rel 0.001 | pass |

- `V2083`: NBSIR 82-2401, Heating Values of Natural Gas and Its Components (Table 14: methane net heat of combustion 802.125 kJ/mol at 288.15 K and 101.325 kPa). The package's formation-enthalpy LHV (water as VAPOUR, gas-phase standard states at 298.15 K) is 802.584 kJ/mol, +0.057% on the printed value - a reference-state difference, not a calculation choice.

## References

- docs/unit-catalogue-plan.md §2 U-C 7

> V2083 checks the methane LHV against NBSIR 82-2401 (802.125 kJ/mol at 288.15 K; package 802.584 kJ/mol on the 298.15 K formation basis, +0.057%).
