# Pump (`pump`)

Family: **flow** · P&ID symbol: `P`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | liquid feed |
| outlet | `outlet` | yes | pressurised liquid (PS flash) |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.pump:Pump` | ΔP/outlet P with efficiency; PS flash on the outlet |
| R1 | planned | — | curve (head/efficiency vs flow) and NPSHa check |

Sizer plugin: `pump`

### R0 parameters

```yaml
properties:
  P_out:
    description: outlet pressure, Pa
    type: number
  eta:
    description: pump efficiency in (0, 1], default 0.65
    type: number
required:
- P_out
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-B 1

> shaft power currently inlined in the unit; the pump_power correlation plugin exists. V1 gap (pump R1) — no open worked example printing a full pump curve plus a fluid state and the resulting P_out or NPSHa was found in the spec's candidate sources (Perry 9th ed. sect. 10, Karassik et al. Pump Handbook 4th ed. ch. 2, Hydraulic Institute ANSI/HI 9.6.1 as citation only, Couper et al. Chemical Process Equipment 3rd ed. ch. 7), so no V1 validation case is supplied; the level is covered by closed-form tests pinned to the spec's printed values (specs/backend/units/pump.md Tests section).
