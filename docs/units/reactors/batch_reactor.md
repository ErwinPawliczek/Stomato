# Batch / semi-batch reactor (`batch_reactor`)

Family: **reactors** · P&ID symbol: `R`

Rigour ladder: R3 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `charge_in` | yes | initial charge |
| outlet | `outlet` | yes | vessel contents at the end of the batch |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R3 | provisional | `ngdesign.units.reactors.batch_reactor:BatchReactor` | one isobaric single-phase batch cycle integrated in time; the inlet is the cycle-averaged charge rate and the outlet the discharge averaged over the cycle. Constant-volume gas batches, semi-batch feeding and a two-phase vessel are not modelled; flowsheet dynamics stay a separate axis |

### R3 parameters

```yaml
properties:
  batch_time_s:
    description: reaction time of one batch
    s: null
    type: number
  bulk_density_kg_m3:
    description: catalyst bulk density
    kg/m3: null
    type: number
  reacting_phase:
    description: the single phase of the vessel; default vapor
    enum:
    - vapor
    - liquid
    type: string
  reaction_set:
    description: inline ReactionSet
    or a string id resolved against Flowsheet.reactions: null
  thermal:
    description: '''isothermal'' | ''adiabatic'' | {duty_W: W, while reacting}; default
      isothermal'
  turnaround_s:
    description: fill, empty and clean time per cycle, s, default 0
    type: number
required:
- reaction_set
- batch_time_s
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-F 7

> A batch cycle over kinetics.rate, not dynamic mode (plan §0 decision 4 still holds for flowsheet dynamics). Provisional on closed-form tests (first-order and second-order with a mole change) and the equivalence to the isobaric PFR; no V1 case was attempted. The semi-batch half of the row name is not implemented.
