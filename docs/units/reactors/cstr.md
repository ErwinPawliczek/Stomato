# Continuous stirred-tank reactor (`cstr`)

Family: **reactors** · P&ID symbol: `R`

Rigour ladder: R1 validated, R2 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `outlet` | yes | reactor effluent (well-mixed) |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R1 | validated | `ngdesign.units.reactors.cstr:CstrR1` | kinetics (Arrhenius, LHHW, power-law), single phase |
| R2 | provisional | `ngdesign.units.reactors.cstr:CstrR2` | multi-phase with VLE in the vessel; the rate runs in one phase at the outlet phase ratio with no slip, and is zero where that phase is absent; reduces to R1 in a single phase |

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

### R2 parameters

```yaml
properties:
  T_guess_K:
    description: Newton start temperature, K
    type: number
  bulk_density_kg_m3:
    description: catalyst bulk density, kg/m3
    type: number
  holdup_m3:
    description: reacting-phase volume, m3; default from the phase ratio
    type: number
  reacting_phase:
    description: phase the reactions occur in; default hc_liquid
    enum:
    - vapor
    - hc_liquid
    - aqueous
    type: string
  reaction_set:
    description: inline ReactionSet
    or a string id resolved against Flowsheet.reactions: null
  thermal:
    description: '''isothermal'' | ''adiabatic'' | {duty_W: W} | {T_out: K}; default
      isothermal'
  volume_m3:
    description: vessel volume, m3
    type: number
required:
- reaction_set
- volume_m3
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-FOGLER-HDA-CSTR` | R1 | `outlet.outlet.composition.H2` | 0.283924 | 0.283923 | abs 1.6e-06 | pass |
| `V1-FOGLER-HDA-CSTR` | R1 | `outlet.outlet.composition.mesitylene` | 0.0923333 | 0.0923324 | abs 1.6e-06 | pass |
| `V1-FOGLER-HDA-CSTR` | R1 | `outlet.outlet.composition.m-xylene` | 0.0992571 | 0.0992584 | abs 1.6e-06 | pass |

- `V1-FOGLER-HDA-CSTR`: Fogler, Elements of Chemical Reaction Engineering, 4th ed., Prentice Hall 2006, Example 6-8, pp. 344-347, Table E6-8.1 (Polymath NLES solution at tau = 0.5 h: C_H 0.0089436, C_M 0.0029085, C_X 0.0031266 lbmol/ft3 from C_H0 0.021, C_M0 0.0105, k1 55.2, k2 30.2 (ft3/lbmol)^0.5/h at 1500 R); scan read 2026-11-04 at https://archive.org/details/elementsofchemicalreactionengineering4thed

## References

- docs/unit-catalogue-plan.md §2 U-F 5

> R1 validated 2026-11-04 on Fogler 4th ed. Example 6-8 (mesitylene hydrodealkylation, two series reactions, Table E6-8.1 NLES solution; V1-FOGLER-HDA-CSTR). That case found and fixed a bug: the rate saw only the positive outlet species and xi = 0 was a depletion corner when an intermediate is not fed (regression test in tests/units/reactors/test_cstr_r1.py). The older V1-gap text below concerns the Ch. 4 liquid examples only. R2 ships provisional on an independent recomputation of the rate from the outlet's own phases and the reduction to R1; no V1 case was attempted. R1 implemented (U-R2): algebraic extents at outlet conditions, damped Newton, single phase in the vessel. V1 gap (2026-10-25; CORRECTION same day: an earlier version of this note wrongly blamed missing components — ethylene oxide, ethylene glycol, propylene oxide and propylene glycol all resolve in ngdesign.data.component_record with formation data, dHf298 = -52680, -389420, -95351.4 and -429800 J/mol, verified this session). The true blockers for the spec's Fogler candidates: (a) the printed isothermal ethylene-glycol CSTR (4th ed. Sec. 4.2, Example 4-2, pp. 142-145: k = 0.311 min-1, stream A 7.67 ft3/min at CA0 = 1 lbmol/ft3, stream B water 7.67 ft3/min, total 15.34 ft3/min, X = 0.8, V = 197.3 ft3 = 1480 gal = 5.6 m3) works volumetrically on a constant-density liquid lbmol/ft3 basis: the water molar flow (hence the inlet mole fractions) is not printed, no pressure is printed, and the printed concentrations are not reachable from the unit's flash-derived c = x·c_tot liquid basis. A probe through CstrR1 at 313 K (feed built with an assumed water density, the one free choice) two-phases the aqueous-EO feed below 10 bar with pr (vapour + liquid, refused at R1) and at all-liquid pressures of 10, 30 and 100 bar liquid-liquid-splits it (two liquid phases; the R1 vapour-fraction check passes such a feed) and the Newton solve does not close the printed V on any of them. (b) The adiabatic propylene-glycol CSTR (non-isothermal chapter) was not re-attempted on this basis. (c) The Ch. 4/5 summary-notes CSTR example (umich.edu/~elements companion site: v0 = 25 dm3/s, CA0 = 0.2 mol/dm3, k = 10 dm3/(mol s), X = 0.9, V = 1125 dm3) is a pure-A liquid at 0.2 mol/dm3, a feed concentration no registry component reproduces. The level ships provisional on its closed-form tests (R1-A, R1-B, identities, refusals).
