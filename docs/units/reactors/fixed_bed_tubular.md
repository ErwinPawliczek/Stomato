# Fixed-bed multi-tubular reactor (`fixed_bed_tubular`)

Family: **reactors** · P&ID symbol: `R`

Rigour ladder: R2 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | tube-side feed |
| outlet | `outlet` | yes | tube-side effluent |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R2 | provisional | `ngdesign.units.reactors.fixed_bed_tubular:FixedBedTubularR2` | pfr R2 tube model with a shell-side coolant balance, co-current or counter-current by shooting on the coolant outlet temperature |

### R2 parameters

```yaml
properties:
  U_W_m2K:
    W/(m2 K): null
    description: overall heat-transfer coefficient on the tube inside area
    type: number
  bed:
    description: '{particle_diameter_m, voidage}; Ergun pressure drop'
    type: object
  bulk_density_kg_m3:
    description: catalyst bulk density
    kg/m3: null
    type: number
  coolant:
    description: '{mass_flow_kg_s, cp_J_kgK, T_in_K, flow: co|counter}; constant-cp
      shell-side coolant'
    type: object
  length_m:
    description: packed tube length
    m: null
    type: number
  n_tubes:
    description: identical parallel tubes
    type: integer
  reacting_phase:
    enum:
    - vapor
    - liquid
    type: string
  reaction_set:
    description: inline ReactionSet
    or a string id resolved against Flowsheet.reactions: null
  tube_diameter_m:
    description: tube inside diameter
    m: null
    type: number
  viscosity_Pa_s:
    description: Ergun viscosity override, Pa s
    type: number
required:
- reaction_set
- n_tubes
- tube_diameter_m
- length_m
- U_W_m2K
- coolant
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-F 8

> The coolant is described by params; the row has no coolant ports. V1 gap - the spec's candidate (Froment, Bischoff & De Wilde 3rd ed. ch. 11, o-xylene to phthalic anhydride) prints its profiles mainly as figures, and figure readings are not valid V1; no copy was consulted. Fogler 4th ed. Ex. 8-5 case 3 (acetone cracking, co-current air heating medium, read 2026-11-04 on the archive.org scan) prints its answers only as Figure E8-5.4 profiles and runs on constant mean Cp (163/83/71 J/mol K), so it is not a V1 case either. Provisional on the epsilon-NTU closed forms and the reduction to pfr R2.
