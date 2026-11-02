# Refluxed absorber / reboiled absorber (`refluxed_absorber`)

Family: **column** · P&ID symbol: `T`

Rigour ladder: R2 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `gas_in` | yes | feed gas |
| inlet | `solvent_in` | yes | lean solvent |
| outlet | `gas_out` | yes | treated gas |
| outlet | `rich_out` | yes | rich solvent |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R2 | provisional | `ngdesign.units.column_shortcut.refluxed_absorber:RefluxedAbsorber` | one-tear MESH with one end exchanger via the column API; partial condenser only (gas_out is a vapour); total condenser refused |

### R2 parameters

```yaml
additionalProperties: false
properties:
  configuration:
    description: reboiled (default; kettle, no condenser) | refluxed (partial condenser,
      no reboiler)
    type: string
  gas_stage:
    description: feed-gas stage (default mid-column reboiled, stage N refluxed)
    type: integer
  n_stages:
    description: equilibrium stages, top = 1 (a partial condenser is stage 1, a kettle
      is stage N)
    minimum: 3
    type: integer
  pressure_profile:
    description: stage pressures, Pa abs (scalar or per-stage list); default gas_in.P
  solvent_stage:
    description: lean-solvent stage (default 1 reboiled, mid-column refluxed); never
      below gas_stage
    type: integer
  spec:
    description: exactly one spec. reboiled = boilup_ratio | bottoms_rate | component_recovery;
      refluxed = distillate_rate (the gas_out flow)
    type: object
required:
- n_stages
- spec
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-E 5
- Seader, Henley & Roper 3rd ed., Table 10.1 (reboiled absorber; refluxed absorber)

> V1 gap — provisional without a case: no printed example with its inputs and product flows was at hand. Covered by a stage-by-stage MESH audit and the zero-duty comparison with absorber R2 (tests/units/column_shortcut/test_refluxed_absorber.py). Measured limits: on the C1/NC4 basis the reboiled bottoms_rate and component_recovery specs do not converge (column core; the boilup_ratio spec does), and the refluxed distillate_rate spec has a narrow window (C2/C3 into NC4: 60 mol/s converges, 75 mol/s does not).
