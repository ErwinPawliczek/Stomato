# Splitter (`splitter`)

Family: **logical** · P&ID symbol: `SPL`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `outlet_1` | yes | first split, fraction of the feed |
| outlet | `outlet_2` | yes | second split, fraction of the feed |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.splitter:Splitter` | splits the feed by fractions or flows; outlet T/P follow the inlet |

### R0 parameters

```yaml
properties:
  fractions:
    description: outlet split fractions (same order as the outlet ports)
    items:
      type: number
    type: array
required:
- fractions
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-A 2

> complete at R0.
