# Adjust (`adjust`)

Family: **logical** · P&ID symbol: `ADJ`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | stream carrying the target |
| outlet | `outlet` | yes | adjusted stream |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.logical.adjust:Adjust` | identity at R0; lowers to a P2-01 DesignSpec (solver.lowering). closed-form only; definitional unit (no open textbook worked example) |

### R0 parameters

```yaml
properties:
  bounds:
    description: '{lower, upper} on the manipulated variable (defaults unbounded)'
    type: object
  manipulate:
    description: '{unit, param} - the unit parameter the solver may vary'
    type: object
  target:
    description: '{stream, variable, value} - the solver target address and value'
    type: object
required:
- target
- manipulate
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-A 5

> exists at solver level only today (plan marks the line 🟡).
