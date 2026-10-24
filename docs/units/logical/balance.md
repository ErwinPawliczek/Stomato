# Balance (`balance`)

Family: **logical** · P&ID symbol: `BAL`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | known streams |
| outlet | `outlet` | yes | stream closed by the balance |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.logical.balance:Balance` | closes one unknown outlet by component balance then a PH flash so energy closes too; negative component flows refused. closed-form only; definitional unit (no open textbook worked example) |

### R0 parameters

```yaml
properties:
  P:
    description: PH-flash pressure of the closed outlet (default inlet P), Pa abs
    type: number
  known_outlets:
    description: FeedSpec kwargs of already-known outlet streams, subtracted per component
    type: array
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-A 6

> roadmap R0.
