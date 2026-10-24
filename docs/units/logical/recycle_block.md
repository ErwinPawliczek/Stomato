# Recycle block (`recycle_block`)

Family: **logical** · P&ID symbol: `RCY`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | torn stream guess |
| outlet | `outlet` | yes | accelerated tear stream |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.logical.recycle_block:RecycleBlock` | identity at R0; lowers to the P2-03 flowsheet tear options (solver.lowering). closed-form only; definitional unit (no open textbook worked example) |

### R0 parameters

```yaml
properties:
  acceleration:
    description: tear acceleration for the loop (default solver value); none = direct
      substitution
    enum:
    - none
    - wegstein
    - broyden
    type: string
  tolerance:
    description: relative tear tolerance (default solver value)
    type: number
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-A 7

> tear handling is implicit in the solver today (P2-03).
