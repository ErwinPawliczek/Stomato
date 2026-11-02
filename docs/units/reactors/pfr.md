# Plug-flow reactor (`pfr`)

Family: **reactors** · P&ID symbol: `R`

Rigour ladder: R1 provisional, R2 provisional, R3 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `outlet` | yes | reactor effluent |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R1 | provisional | `ngdesign.units.reactors.pfr:PfrR1` | kinetic extents integrated over V (BDF, depletion and pressure-floor events); the RHS never flashes — single-phase properties come from phase_props and the audit flashes once per output point, so the flash count is O(n_output) and independent of V (P0-06); the outlet closes exactly on the formation-enthalpy basis and info carries extents, T_profile_out_K, T_closure_gap_K, T_max_K, V_at_T_max_m3. The energy ODE uses the closure-consistent dH (PR #311 review, blocking items 1 and B: heat_of_reaction at 298.15 K plus stoichiometric partial molar enthalpies of the actual mixture, from a finite difference of the mixture enthalpy flow); the residual T_closure_gap_K measures 6.6e-7 K on ideal-raoult for the nC4 isomerisation case, within the spec's 1e-3 K consistency bound |
| R2 | provisional | `ngdesign.units.reactors.pfr:PfrR2` | extents, energy and pressure integrated along the tube with Ergun (fluids.packed_bed.Ergun) and wall heat transfer to a fixed coolant temperature; the outlet closes on the formation basis at P_out; reduces to R1 with no bed, no coolant and the same volume |
| R3 | provisional | `ngdesign.units.reactors.pfr:PfrR3` | R2 with the rate multiplied by a*eta; generalized Thiele modulus eta = tanh(phi)/phi on a shape-normalized sphere and separable power-law activity decay, uniform along the bed |

### R1 parameters

```yaml
properties:
  bulk_density_kg_m3:
    description: "catalyst bulk density, kg/m3 \u2014 required when a rate is per\
      \ kg_cat"
    type: number
  reacting_phase:
    description: '''vapor'' | ''liquid'' (default vapor); the PFR is single-phase
      and a two-phase state anywhere along the profile is refused'
  reaction_set:
    description: inline ReactionSet, or a string id resolved against Flowsheet.reactions
  thermal:
    description: '''isothermal'' | ''adiabatic'' | {duty_W: W} (default isothermal;
      {T_out: K} is a conversion-reactor mode, refused for a kinetic PFR)'
  volume_m3:
    description: reactor volume, m3 (> 0)
    type: number
type: object
```

### R2 parameters

```yaml
properties:
  bed:
    description: '{particle_diameter_m, voidage}; present means Ergun pressure drop'
    type: object
  bulk_density_kg_m3:
    description: catalyst bulk density
    kg/m3: null
    type: number
  length_m:
    description: tube length
    m: null
    type: number
  n_tubes:
    description: parallel identical tubes, default 1
    type: integer
  reacting_phase:
    description: single phase the flow must stay in
    enum:
    - vapor
    - liquid
    type: string
  reaction_set:
    description: inline ReactionSet
    or a string id resolved against Flowsheet.reactions: null
  thermal:
    description: '''isothermal'' | ''adiabatic'' | {duty_W: W} | {coolant_T_K: K,
      U_W_m2K: W/m2K}; default isothermal'
  tube_diameter_m:
    description: tube inside diameter
    m: null
    type: number
  viscosity_Pa_s:
    description: Ergun viscosity override, Pa s; required when the package reports
      none
    type: number
required:
- reaction_set
- tube_diameter_m
- length_m
type: object
```

### R3 parameters

```yaml
properties:
  bed:
    description: '{particle_diameter_m, voidage}; a pellet needs voidage'
    type: object
  bulk_density_kg_m3:
    description: catalyst bulk density
    kg/m3: null
    type: number
  deactivation:
    description: '{order, k_d_per_s, time_on_stream_s}; power-law decay frozen at
      the time on stream'
    type: object
  effectiveness:
    description: '{reaction_id: eta in (0, 1]}; overrides the Thiele modulus'
    type: object
  length_m:
    description: tube length
    m: null
    type: number
  n_tubes:
    description: parallel identical tubes, default 1
    type: integer
  pellet:
    description: '{radius_m, effective_diffusivity_m2_s}; sphere, Thiele effectiveness
      per power-law reaction'
    type: object
  reacting_phase:
    description: single phase the flow must stay in
    enum:
    - vapor
    - liquid
    type: string
  reaction_set:
    description: inline ReactionSet
    or a string id resolved against Flowsheet.reactions: null
  thermal:
    description: as R2
  tube_diameter_m:
    description: tube inside diameter
    m: null
    type: number
  viscosity_Pa_s:
    description: Ergun viscosity override, Pa s
    type: number
required:
- reaction_set
- tube_diameter_m
- length_m
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-F 6

> R1, R2 and R3 implemented; single phase. R2 and R3 ship provisional on the spec's hand calculations (Fogler eq. 4-33 Ergun, wall-exchange exponential, Thiele/activity closed form) and the reductions to the lower level; no V1 case was attempted for them. R1 V1 gap — no transcribable printed validation case: searches 'Fogler Elements of Chemical Reaction Engineering PFR example first order irreversible gas phase numerical conversion worked example printed values' and 'Example 4- Fogler PFR gas phase 500 K volume final conversion table printed' found only umich web self-test pages and a 4th-ed chapter PDF snippet, none with a full feed/kinetics/outlet state reproducible without reconstruction
