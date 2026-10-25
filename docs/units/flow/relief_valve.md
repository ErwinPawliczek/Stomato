# Relief valve (`relief_valve`)

Family: **flow** · P&ID symbol: `PSV`

Rigour ladder: R0 provisional, R1 provisional, R2 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | relieved stream at set pressure |
| outlet | `outlet` | yes | discharge |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.flow.relief_valve:ReliefValve` | set pressure, orifice from API 520 (the psv_api520_gas correlation plugin exists) |
| R1 | provisional | `ngdesign.units.flow.relief_valve_r1:ReliefValveR1` | Leung omega two-phase and subcooled sizing (eqs. 1-5), gas delegated to R0; Kd by regime |
| R2 | provisional | `ngdesign.units.flow.relief_valve_r2:ReliefValveR2` | rated-capacity inlet-loss and built-up back-pressure checks with bellows Kb/Kw re-sizing |

### R1 parameters

```yaml
properties:
  Kb:
    description: back-pressure correction, default 1.0
    type: number
  Kc:
    description: combination (rupture disk) correction, default 1.0
    type: number
  Kd:
    description: discharge coefficient; default 0.975 gas / 0.85 two-phase / 0.65
      liquid, chosen by regime
    type: number
  Kv:
    description: viscosity correction (liquid), default 1.0
    type: number
  Kw:
    description: liquid back-pressure correction (balanced bellows), default 1.0
    type: number
  P_back:
    description: superimposed back pressure, Pa abs
    type: number
required:
- P_back
type: object
```

### R2 parameters

```yaml
properties:
  D_in_m:
    description: inlet line ID, m
    type: number
  D_out_m:
    description: discharge line ID, m
    type: number
  K_in:
    description: inlet line sum-K
    type: number
  K_out:
    description: discharge line sum-K
    type: number
  Kb:
    description: back-pressure correction, default 1.0
    type: number
  Kc:
    description: combination (rupture disk) correction, default 1.0
    type: number
  Kd:
    description: discharge coefficient; default 0.975 gas / 0.85 two-phase / 0.65
      liquid
    type: number
  Kv:
    description: viscosity correction (liquid), default 1.0
    type: number
  Kw:
    description: liquid back-pressure correction (balanced bellows), default 1.0
    type: number
  L_in_m:
    description: inlet line length, m
    type: number
  L_out_m:
    description: discharge line length, m
    type: number
  P_atm:
    description: atmospheric pressure, Pa, default 101325
    type: number
  P_back:
    description: superimposed back pressure, Pa abs
    type: number
  P_set:
    description: set pressure, Pa abs
    type: number
  overpressure:
    description: overpressure fraction, one of 0.10, 0.16, 0.21
    type: number
  roughness_in_m:
    description: inlet roughness, m, default 4.57e-5 commercial steel
    type: number
  roughness_out_m:
    description: discharge roughness, m, default 4.57e-5 commercial steel
    type: number
  valve_type:
    description: conventional, balanced_bellows or pilot
    type: string
required:
- P_back
- P_set
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-B 7

> R0 gas PSV sizing per API 520 Part I with API 526 orifice selection. V1 gap (PR
