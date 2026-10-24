# Membrane (gas) (`membrane`)

Family: **separation** · P&ID symbol: `M`

Rigour ladder: R0 provisional, R1 planned, R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed_in` | yes | high-pressure feed gas |
| outlet | `permeate` | yes | permeate stream |
| outlet | `residue` | yes | residue stream |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.separation.membrane:Membrane` | exactly one of permeate_recovery (any components) and stage_cut with perm_ratio (binary Weller-Steiner complete mixing); the permeate leaves at P_permeate, the residue at P_in. Evidence gap — the stage-cut model is validated against Geankoplis Ex. 13.4-2 (air, y_O2 = 0.5068, reject x_O2 = 0.1345); the permeate_recovery path is a spec split with V0 self-consistency only. |
| R1 | planned | — | solution-diffusion with permeances, cross-flow |
| R2 | planned | — | counter-current module |

### R0 parameters

```yaml
properties:
  P_permeate:
    description: permeate-side absolute pressure, Pa; required
    type: number
  perm_ratio:
    description: component id to relative permeance; required with stage_cut (binary)
    type: object
  permeate_recovery:
    description: component id to the fraction of its molar flow crossing to the permeate;
      unnamed components stay in the residue
    type: object
  stage_cut:
    description: fraction of the feed molar flow recovered as permeate (binary Weller-Steiner
      model)
    maximum: 1
    minimum: 0
    type: number
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-membrane-geankoplis-13-4-2` | R0 | `outlet.permeate.composition.O2` | 0.5068 | 0.506809 | abs 0.0001 | pass |
| `V1-membrane-geankoplis-13-4-2` | R0 | `outlet.residue.composition.O2` | 0.1345 | 0.134548 | abs 0.0001 | pass |

- `V1-membrane-geankoplis-13-4-2`: Geankoplis, "Transport Processes and Separation Process Principles", 4th ed., Example 13.4-2 "Membrane Design for Separation of Air" (p. 767): an air feed (z_O2 = 0.209) at 190 cmHg with the permeate side at 19 cmHg (pressure ratio 10), alpha = 10 (O2 permeability / N2 permeability) and stage cut theta = 0.2 give a permeate y_O2 = 0.5068 and a reject x_O2 = 0.1345 by the Weller-Steiner complete-mixing model. Numbers read from the FOSSEE open transcription of Geankoplis Ch. 13 (tbc-python.fossee.in, GeankoplisChapter13, Example 13.4-2). The compositions come from the complete-mixing algebra alone (thermo only sets the outlet states), so no equation-of-state gap applies; the tolerances are the book's four-decimal rounding.

## References

- docs/unit-catalogue-plan.md §2 U-D 8

> R0 split and stage-cut specs implemented; Geankoplis Ex. 13.4-2 example.
