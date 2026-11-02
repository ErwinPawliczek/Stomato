# Batch distillation (`batch_distillation`)

Family: **column** · P&ID symbol: `T`

Rigour ladder: R3 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `charge` | yes | initial charge |
| outlet | `distillate` | yes | accumulated distillate |
| outlet | `residue` | yes | pot residue |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R3 | provisional | `ngdesign.units.column_shortcut.batch_distillation:BatchDistillation` | Rayleigh differential distillation over thermo.bubble_point (one pot, no rectification, no holdup); cumulative distillate and residue; the charge flow is a campaign average, no batch time is modelled |

### R3 parameters

```yaml
additionalProperties: false
properties:
  P:
    description: pot pressure, Pa abs (default charge P)
    exclusiveMinimum: 0
    type: number
  fraction_distilled:
    description: 'stop condition: moles boiled off per mole charged'
    exclusiveMaximum: 1
    exclusiveMinimum: 0
    type: number
required:
- fraction_distilled
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-E 12
- Rayleigh, Phil. Mag. 4 (1902) 521
- Doherty & Perkins, Chem. Eng. Sci. 33 (1978) 281

> The dynamic axis of plan §0 decision 4 is not built: this level is the integrated Rayleigh balance, not a holdup simulation. V1 gap — provisional without a case; the level is anchored to the closed-form constant-alpha Rayleigh equation through a stub saturation surface (tests/units/column_shortcut/test_batch_distillation.py).
