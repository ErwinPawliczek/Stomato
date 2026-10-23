# Rigorous distillation column (`column`)

Family: **column** · P&ID symbol: `T`

Rigour ladder: R2 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed` | yes | main feed (further feeds via params) |
| outlet | `distillate` | yes | overhead product (total condenser) or vapour overhead (partial) |
| outlet | `bottoms` | yes | bottoms product |
| outlet | `side_draw` | yes | side draw (zero-flow state when no draw is configured) |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R2 | provisional | `ngdesign.units.column:Column` | MESH on the inside-out (Boston-Sullivan) solver with Naphtali-Sandholm fallback; configurations (absorber zero-tear, stripper/rectifier one-tear, two-tear distillation) select themselves from the condenser/reboiler kinds |

### R2 parameters

```yaml
properties:
  condenser:
    description: total | partial (total condenses above stage 1)
    type: string
  feed_stage:
    description: main feed stage
    type: integer
  feeds:
    description: additional feeds by stage
    type: object
  n_stages:
    description: equilibrium stages, numbered 1..N top to bottom
    type: integer
  pressure_profile:
    description: top pressure or per-stage profile, Pa
    type: number
  reboiler:
    description: kettle | none (none = absorber/rectifier configuration)
    type: string
  side_draws:
    description: additional draws by stage
    type: object
  specs:
    description: two specs for two tears (reflux_ratio, distillate_rate, boilup, ...);
      one for one-tear; none for an absorber
    type: object
required:
- n_stages
- condenser
- reboiler
- feed_stage
- specs
type: object
```

Mode map: `distillation` → `R2`, `absorber` → `R2`, `stripper` → `R2`, `rectifier` → `R2`, `reboiled_absorber` → `R2`

## References

- Boston & Sullivan 1974, Can. J. Chem. Eng. 52, 52-63
- Naphtali & Sandholm 1971, AIChE J. 17(1), 148-153
- docs/unit-catalogue-plan.md §2 U-E 2

> covers plan U-E 2 and the R2 of U-E 3 (feed-determined absorber, zero-tear) and U-E 4 (reboiled stripper, one-tear) as configurations; rate-based stages (plan's R3 column) are a later round on their own ladder. Side draws exist (side_draw port); pumparounds and multiple feeds beyond the params hooks are the column_extensions row.
