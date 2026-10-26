# Flash drum with duty (`flash_drum`)

Family: **separation** · P&ID symbol: `V`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| inlet | `inlet_2` | no | optional second feed; the inlets are adiabatically PH-mixed at the lowest inlet pressure before the outlet spec applies |
| outlet | `gas_out` | yes | vapour outlet |
| outlet | `liquid_out` | yes | non-aqueous liquid outlet (the whole liquid when the package returns one) |
| outlet | `aqueous_out` | no | aqueous liquid outlet (zero flow when the package returns a single liquid) |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.separation.flash_drum:FlashDrum` | PT / PH (duty_W) / PVF flash at the outlet pressure — exactly one of duty_W and vapor_fraction; the inlets are first adiabatically PH-mixed at the lowest inlet pressure (a single inlet passes through unchanged); the balancing duty is reported; gas, liquid and (when the package gives one) aqueous outlets at their flash states |
| R1 | provisional | `ngdesign.units.separation.flash_drum_r1:FlashDrumR1` | Souders-Brown sizing (York demister K) and droplet carry-over at a given diameter over both liquid outlets; reduces to R0 without diameter_m or at E = 0 |

### R0 parameters

```yaml
properties:
  duty_W:
    description: heat added to the drum, W; PH flash with H_out = H_in + duty_W
    type: number
  outlet_P:
    description: outlet pressure, Pa abs; default min inlet P
    type: number
  vapor_fraction:
    description: molar vapour fraction; PVF flash at outlet_P
    maximum: 1
    minimum: 0
    type: number
type: object
```

### R1 parameters

```yaml
properties:
  K_m_s:
    description: Souders-Brown K, m/s; default York demister fit at the drum pressure
    exclusiveMinimum: 0
    type: number
  diameter_m:
    description: vessel inside diameter, m; enables the carry-over calculation
    exclusiveMinimum: 0
    type: number
  droplet_d_rr_m:
    description: Rosin-Rammler characteristic droplet size, m
    exclusiveMinimum: 0
    type: number
  droplet_n_rr:
    description: Rosin-Rammler spread parameter
    exclusiveMinimum: 0
    type: number
  duty_W:
    description: heat added to the drum, W; PH flash with H_out = H_in + duty_W
    type: number
  gas_viscosity_Pa_s:
    description: gas viscosity override, Pa s
    exclusiveMinimum: 0
    type: number
  inlet_entrained_fraction:
    description: fraction of the liquid entering the gravity section as droplets
    maximum: 1
    minimum: 0
    type: number
  outlet_P:
    description: outlet pressure, Pa abs; default min inlet P
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
| `V1-flash-corripio-2013` | R0 | `outlet.gas_out.T` | 355.05 | 357.382 | abs 0.1 | assessed miss |

- `V1-flash-corripio-2013`: Corripio, "Flash Distillation" lecture notes (2013), Example 1: 38 wt% propane / balance n-octane (z = 0.614 / 0.386 molar, 802 kmol/h = 222.78 mol/s), drum at 3.5 atm with V/F = 0.61 gives T = 81.9 degC, y_C3 = 0.937 by ideal-K (Antoine, Reid-Sherwood-Prausnitz). The tolerance is the book's rounding of 81.9 degC (+/- 0.1 K on 355.05 K), fixed before the run. The catalogue PR package is expected to sit above the book's ideal-K route; the measured miss is recorded in `assessed`, never absorbed by the tolerance.
  - assessed: Measured miss (PR package, this case's feeds and params): T = 357.382 K (84.23 degC), 2.33 K above the book's 355.05 K; y_C3 = 0.9213 vs the printed 0.937. Cause: the book solves the Rachford-Rice isothermal flash with ideal K-values from Antoine constants (Reid-Sherwood-Prausnitz), while the catalogue package is Peng-Robinson, whose C3/nC8 K-values at these conditions are less ideal; the PVF spec then lands at a higher T. The book's own rounding (+/- 0.1 K) is kept as the tolerance; the miss is the model gap, reported here rather than absorbed.

## References

- docs/unit-catalogue-plan.md §2 U-D 3

> R0 PT/PH/PVF flash implemented with an optional mixed second inlet; the flash family is validated by V1-flash-corripio-2013 (assessed PR-vs-ideal-K miss) and V0 self-consistency; Souders-Brown sizing is R1.
