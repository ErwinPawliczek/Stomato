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

> R1 implemented (U-R2): algebraic extents at outlet conditions, damped Newton, single phase in the vessel. V1 gap (2026-10-25; CORRECTION same day: an earlier version of this note wrongly blamed missing components — ethylene oxide, ethylene glycol, propylene oxide and propylene glycol all resolve in ngdesign.data.component_record with formation data, dHf298 = -52680, -389420, -95351.4 and -429800 J/mol, verified this session). The true blockers for the spec's Fogler candidates: (a) the printed isothermal ethylene-glycol CSTR (4th ed. Sec. 4.2, Example 4-2, pp. 142-145, numbers read from a scanned copy this session: k = 0.311 min-1, stream A 7.67 ft3/min at CA0 = 1 lbmol/ft3, stream B water 7.67 ft3/min, total 15.34 ft3/min, X = 0.8, V = 197.3 ft3 = 1480 gal = 5.6 m3) works volumetrically on a constant-density liquid lbmol/ft3 basis: the water molar flow (hence the inlet mole fractions) is not printed, no pressure is printed, and the printed concentrations are not reachable from the unit's flash-derived c = x·c_tot liquid basis. A probe through CstrR1 at 313 K (feed built with an assumed water density, the one free choice) two-phases the aqueous-EO feed below 10 bar with pr (vapour + liquid, refused at R1) and at all-liquid pressures of 10, 30 and 100 bar liquid-liquid-splits it (two liquid phases; the R1 vapour-fraction check passes such a feed) and the Newton solve does not close the printed V on any of them. (b) The adiabatic propylene-glycol CSTR (non-isothermal chapter) was not re-attempted on this basis. (c) The Ch. 4/5 summary-notes CSTR example (umich.edu/~elements companion site: v0 = 25 dm3/s, CA0 = 0.2 mol/dm3, k = 10 dm3/(mol s), X = 0.9, V = 1125 dm3) is a pure-A liquid at 0.2 mol/dm3, a feed concentration no registry component reproduces. The level ships provisional on its closed-form tests (R1-A, R1-B, identities, refusals).
