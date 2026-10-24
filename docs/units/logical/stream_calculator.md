# Stream calculator (set) (`stream_calculator`)

Family: **logical** · P&ID symbol: `SMC`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | reference stream |
| outlet | `outlet` | yes | copy/scale/override of the inlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.logical.stream_calculator:StreamCalculator` | scale, set overrides, then a PT flash; duty = enthalpy change. closed-form only; definitional unit (no open textbook worked example; searched Towler & Sinnott ch. 2 and Coulson & Richardson vol. 2) |

### R0 parameters

```yaml
properties:
  scale:
    description: multiplies the inlet flow (default 1)
    type: number
  set:
    description: overrides applied before a PT flash; T (K), P (Pa), molar_flow (mol/s),
      composition (renormalised, negative entries refused)
    type: object
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-A 4

> P2-01 design specs exist at the solver level; the unit form is missing.
