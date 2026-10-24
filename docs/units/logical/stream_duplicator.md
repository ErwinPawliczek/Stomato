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
| R0 | provisional | `ngdesign.units.logical.stream_duplicator:StreamDuplicator` | reference-stream tees: copy_0 carries the material, copies 1..N-1 share the intensive state at copy_flow_scale. closed-form only; definitional unit (no open textbook worked example) |

### R0 parameters

```yaml
properties:
  allow_unbalanced:
    description: permit the full-flow mirror form that breaks the mole balance (V0
      never uses it)
    type: boolean
  copy_flow_scale:
    description: flow scale of copies 1..N-1 (default 0 so the balance closes)
    type: number
  n_copies:
    description: number of outlets (default 2)
    type: integer
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-A 8

> roadmap R0.
