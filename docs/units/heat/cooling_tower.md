# Cooling tower (`cooling_tower`)

Family: **heat** · P&ID symbol: `CT`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `water_in` | yes | warm circulating water |
| inlet | `air_in` | yes | inlet air (humid, N2/O2 dry basis) |
| outlet | `water_out` | yes | cooled water |
| outlet | `air_out` | yes | exit air (saturated at the exit-air temperature solved from the energy balance) |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.heat.cooling_tower:CoolingTower` | water outlet FIXED at wet bulb + approach_K; the exit air, saturated at the exit-air temperature solved from the overall energy closure, carries the heat and the evaporation; blowdown/makeup from cycles of concentration |
| R1 | provisional | `ngdesign.units.heat.cooling_tower_r1:CoolingTowerR1` | Merkel number by 4-point Chebyshev (CTI ATC-105) against KaV/L = C (L/G)^-n, water outlet solved by brentq, then the R0 balance at the solved approach; Merkel enthalpies from the ASHRAE Fundamentals Ch. 1 Hyland-Wexler closed form per the orchestrator ruling on PR #284 (the package's water latent heat is ~4% high, #249), the balance stays R0's through the thermo package; approach_K is solved at R1, not a parameter. A characteristic above the attainable Merkel number refuses typed with both numbers. |

### R0 parameters

```yaml
properties:
  approach_K:
    description: water outlet above the inlet-air wet bulb, K (> 0, required)
    type: number
  cycles_of_concentration:
    description: cycles of concentration, >= 1 (default 3)
    type: number
type: object
```

### R1 parameters

```yaml
properties:
  characteristic_C:
    description: tower characteristic coefficient C in KaV/L = C (L/G)^-n (solution
      mode, with characteristic_n)
    exclusiveMinimum: 0
    type: number
  characteristic_n:
    description: tower characteristic exponent n, >= 0 (solution mode, with characteristic_C)
    type: number
  cycles_of_concentration:
    description: cycles of concentration, >= 1 (default 3)
    minimum: 1
    type: number
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V2085` | R0 | `info.wet_bulb_K` | 293.15 | 292.989 | abs 0.2 | pass |

- `V2085`: ASHRAE Fundamentals 2021, SI edition, Ch. 1 Psychrometrics, Example 1: 40 C dry bulb, 20 C thermodynamic wet bulb, 101.325 kPa; chart humidity ratio 6.5 g_w/kg_da -> y = 0.010343 mol/mol. The case runs the tower on the printed air state and checks the model wet bulb against the printed 293.15 K; the water and air flows are carrier sizes, not cited values, and no model output beyond the wet bulb is compared.

## References

- docs/unit-catalogue-plan.md §2 U-C 8

> V2085 checks the model wet bulb against ASHRAE Fundamentals 2021 SI Ch. 1 Example 1 (40 C dry-bulb / 20 C wet-bulb air; measured 292.989 K, -0.16 K). R1 V1 gap — searched ASHRAE HVAC S&E Ch. 40, Perry's 8th §12, Kern 1950 Ch. 17; the printed worked examples sit behind paywalls, the web reproduces the method but not the printed inputs/answers, so no printed-value case is constructed.
