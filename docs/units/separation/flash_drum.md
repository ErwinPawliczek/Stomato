# Flash drum with duty (`flash_drum`)

Family: **separation** · P&ID symbol: `V`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `gas_out` | yes | vapour outlet |
| outlet | `liquid_out` | yes | non-aqueous liquid outlet (the whole liquid when the package returns one) |
| outlet | `aqueous_out` | no | aqueous liquid outlet (zero flow when the package returns a single liquid) |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.separation.flash_drum:FlashDrum` | PT / PH (duty_W) / PVF flash at the outlet pressure — exactly one of duty_W and vapor_fraction; the balancing duty is reported; gas, liquid and (when the package gives one) aqueous outlets at their flash states |
| R1 | planned | — | Souders-Brown sizing, carry-over at a given diameter (the souders_brown correlation plugin exists) |

### R0 parameters

```yaml
properties:
  duty_W:
    description: heat added to the drum, W; PH flash with H_out = H_in + duty_W
    type: number
  outlet_P:
    description: outlet pressure, Pa abs; default inlet P
    type: number
  vapor_fraction:
    description: molar vapour fraction; PVF flash at outlet_P
    maximum: 1
    minimum: 0
    type: number
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V-flash-corripio-2013` | R0 | — | — | — | — | error: FlashDrumSpecError: give exactly one of duty_W and vapor_fraction, not both |

- `V-flash-corripio-2013`: Corripio, "Flash Distillation" lecture notes (2013), Example 1: 38 wt% propane / balance n-octane (z = 0.614 / 0.386 molar, 802 kmol/h), drum at 3.5 atm with V/F = 0.61 gives T = 81.9 degC, y_C3 = 0.937 by ideal-K (Antoine, Reid-Sherwood-Prausnitz). This case runs the same PVF spec on the catalogue PR package, which sits ~2.3 K above the ideal-K route; the tolerance covers that model gap, fixed before the run.

## References

- docs/unit-catalogue-plan.md §2 U-D 3

> roadmap; the S2 amine loop needs it (plan §2b).
