# Fan / blower (`fan`)

Family: **flow** · P&ID symbol: `FAN`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | gas feed |
| outlet | `outlet` | yes | raised-pressure gas |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.flow.fan:Fan` | ΔP + efficiency |
| R1 | provisional | `ngdesign.units.flow.fan_r1:FanR1` | performance curve (pressure rise/efficiency vs flow, PCHIP) with fan laws and density correction |

### R1 parameters

```yaml
properties:
  curve:
    properties:
      efficiency:
        description: efficiency at each point, (0, 1]
        items:
          type: number
        type: array
      flow_m3_s:
        description: actual inlet flow points, m3/s, strictly increasing
        items:
          type: number
        type: array
      pressure_rise_Pa:
        description: fan total pressure rise at each point, Pa
        items:
          type: number
        type: array
    required:
    - flow_m3_s
    - pressure_rise_Pa
    - efficiency
    type: object
  curve_density_kg_m3:
    description: rating density of the curve, kg/m3; omitted = operating density
    type: number
  speed_ratio:
    description: N / N_curve (fan laws), default 1.0
    type: number
required:
- curve
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-B 11

> R0 fixed dP rise with efficiency; R1 performance curve (PCHIP, no extrapolation) with fan laws (AMCA 201; ASHRAE Fans chapter) and density correction, delegating to R0. V1 gap (fan R1) - no open printed fan-law worked example qualified for the harness — searched AMCA 201 (its fan-selection example needs manufacturer data, not printed results), the openly accessible ASHRAE Handbook—Fundamentals ch. 21 speed-change example (its only printed input is a single curve point, so a case would need a synthesized curve and would restate the fan law — the circularity that withdrew the ejector case), ASHRAE HVAC Systems & Equipment Fans chapter (paywalled) and Perry's 9th ed. sect. 10 (no printed worked example found). Covered by closed-form tests instead.
