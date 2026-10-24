# Stream duplicator / tee (`stream_duplicator`)

Family: **logical** · P&ID symbol: `TEE`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `outlet_1` | yes | identical copy |
| outlet | `outlet_2` | yes | identical copy |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.logical.stream_duplicator:StreamDuplicator` | reference-stream tees: outlet_1 carries the material, outlet_2 shares the intensive state at copy_flow_scale. closed-form only; definitional unit (no open textbook worked example) |

### R0 parameters

```yaml
properties:
  allow_unbalanced:
    description: permit the full-flow mirror form that breaks the mole balance (V0
      never uses it)
    type: boolean
  copy_flow_scale:
    description: flow scale of outlet_2 (default 0 so the balance closes)
    type: number
  n_copies:
    description: number of outlets; R0 refuses any value other than 2 (the row declares
      exactly two ports)
    type: integer
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-A 8

> roadmap R0.
