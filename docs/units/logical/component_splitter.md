# Component splitter (`component_splitter`)

Family: **logical** · P&ID symbol: `CSP`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `outlet_1` | yes | first component split |
| outlet | `outlet_2` | yes | second component split |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.logical.component_splitter:ComponentSplitter` | per-component split fractions via units._physics.splitting, each outlet flashed at its own T/P; duty reported. closed-form only; definitional unit (no open textbook worked example; searched Towler & Sinnott ch. 2 and Coulson & Richardson vol. 2) |

### R0 parameters

```yaml
properties:
  fractions:
    description: cid -> fraction of its flow sent to outlet_1; unmapped cids go to
      outlet_2
    type: object
  outlet_P:
    description: outlet pressure, scalar or per port (outlet_1/outlet_2), Pa abs
    type:
    - number
    - object
  outlet_T:
    description: outlet temperature, scalar or per port (outlet_1/outlet_2), K
    type:
    - number
    - object
required:
- fractions
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-A 3

> roadmap R0 — the canvas slice S3 needs it (plan §2b).
