# Continuous stirred-tank reactor (`cstr`)

Family: **reactors** · P&ID symbol: `R`

Rigour ladder: R1 provisional, R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `outlet` | yes | reactor effluent (well-mixed) |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R1 | provisional | `ngdesign.units.reactors.cstr:CstrR1` | kinetics (Arrhenius, LHHW, power-law), single phase |
| R2 | planned | — | multi-phase with VLE in the vessel |

### R1 parameters

```yaml
properties:
  T_guess_K:
    K; selects the steady-state branch: null
    description: Newton start temperature
    type: number
  bulk_density_kg_m3:
    description: catalyst bulk density
    kg/m3: null
    type: number
  reacting_phase:
    description: single phase required at R1; default vapor
    enum:
    - vapor
    - liquid
    type: string
  reaction_set:
    description: inline ReactionSet
    or a string id resolved against Flowsheet.reactions: null
  thermal:
    description: '''isothermal'' | ''adiabatic'' | {duty_W: W} | {T_out: K}; default
      isothermal'
  volume_m3:
    description: reacting volume
    m3: null
    type: number
required:
- reaction_set
- volume_m3
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-F 5

> R1 implemented (U-R2): algebraic extents at outlet conditions, damped Newton, single phase in the vessel. V1 gap (2026-10-25): the spec's Fogler candidates need components absent from the open registry — the isothermal ethylene-glycol CSTR (4th ed. ch. 4 / 5th ed. p. 157-160, IDAES transcription) needs ethylene oxide and ethylene glycol, the adiabatic propylene-glycol CSTR (non-isothermal chapter) needs propylene oxide; the Ch. 4/5 summary-notes CSTR example (umich.edu/~elements companion site: v0 = 25 dm3/s, CA0 = 0.2 mol/dm3, k = 10 dm3/(mol s), X = 0.9, V = 1125 dm3) is a pure-A liquid at 0.2 mol/dm3, a feed concentration no registry component reproduces. The level ships provisional on its closed-form tests (R1-A, R1-B, identities, refusals).
