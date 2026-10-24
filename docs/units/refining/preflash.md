# Preflash / flash column (`preflash`)

Family: **refining** · P&ID symbol: `FL`

Rigour ladder: R0 provisional, R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed_in` | yes | heated assay feed |
| outlet | `vapor_out` | yes | flashed vapor |
| outlet | `liquid_out` | yes | flashed liquid |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.refining.preflash:Preflash` | flash drum on the assay stream (spec U-H1 PT flash at the drum conditions; vapour to vapor_out, pooled liquid to liquid_out) |
| R2 | planned | — | short MESH |

### R0 parameters

```yaml
properties:
  P:
    description: drum pressure (Pa abs, default the inlet pressure)
    type: number
  T:
    description: drum temperature (K)
    type: number
required:
- T
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V2105` | R0 | `info.vapor_frac` | 0.44867 | 0.448666 | rel 0.005 | pass |
| `V2105` | R0 | `outlet.vapor_out.P` | 250000 | 250000 | abs 1e-06 | pass |
| `V2105` | R0 | `outlet.liquid_out.P` | 250000 | 250000 | abs 1e-06 | pass |

- `V2105`: Flash at the adapter example's published drum conditions, 232 degC / 2.5 bar (Gary et al., Petroleum Refining, p. 66). The open sources print no flashed-vapour yield for this basis, so the vapour fraction is a regression pin computed by the registered PR package at those conditions; the drum pressure on both outlets is the closed-form plumbing check

## References

- docs/unit-catalogue-plan.md §2 U-H 6

> roadmap.
