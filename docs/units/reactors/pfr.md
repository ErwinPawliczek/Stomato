# Plug-flow reactor (`pfr`)

Family: **reactors** · P&ID symbol: `R`

Rigour ladder: R1 provisional, R2 provisional, R3 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `outlet` | yes | reactor effluent |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R1 | provisional | `ngdesign.units.reactors.pfr:PfrR1` | kinetic extents integrated over V (BDF, depletion and pressure-floor events); the RHS never flashes — single-phase properties come from phase_props and the audit flashes once per output point, so the flash count is O(n_output) and independent of V (P0-06); the outlet closes exactly on the formation-enthalpy basis and info carries extents, T_profile_out_K, T_closure_gap_K, T_max_K, V_at_T_max_m3. The energy ODE uses the closure-consistent dH (PR #311 review, blocking items 1 and B: heat_of_reaction at 298.15 K plus stoichiometric partial molar enthalpies of the actual mixture, from a finite difference of the mixture enthalpy flow); the residual T_closure_gap_K measures 6.6e-7 K on ideal-raoult for the nC4 isomerisation case, within the spec's 1e-3 K consistency bound |
| R2 | provisional | `ngdesign.units.reactors.pfr:PfrR2` | the R1 kinetics integrator over n_tubes·A_c·L plus the R2 physics (spec step 5): the Ergun pressure drop of the packed bed with a 90 % inlet-pressure floor event, and wall heat to a coolant at fixed temperature via the shared HeatModel hook (q_V = U·(4/Dt)·(T_c - T)). The audit flashes once per output point; a two-phase state anywhere along the profile is refused. The R2-b closed form (inert N2, c_p at the film mean 302.5 K: T_out = 301.303674 K, Q = -10.7981558 W) is verified in tests at 2e-4 K; the R2->R1 reduction identity (same kinetics, no bed, isothermal, no wall) reproduces the R1-A result. Refusals: geometry outside bounds, rate_units outside the PowerLaw lists, a per-kg_cat rate without bulk_density_kg_m3, a reaction with no kinetics, an LHHW rate with an equilibrium model, a bed without viscosity, voidage outside (0, 1), a pressure drop past the 90 % floor, an unknown thermal mode, and a two-phase state |
| R3 | planned | — | catalyst deactivation, pellet effectiveness |

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
    description: "{particle_diameter_m: m, voidage: (-)} \u2014 packed bed for the\
      \ Ergun pressure drop (spec equation 8); required for any pressure drop, voidage\
      \ strictly inside (0, 1)"
  bulk_density_kg_m3:
    description: "catalyst bulk density, kg/m3 \u2014 required when a rate is per\
      \ kg_cat"
    type: number
  length_m:
    description: tube length, m (> 0)
    type: number
  n_tubes:
    description: number of parallel tubes (default 1, >= 1)
    type: integer
  reacting_phase:
    description: '''vapor'' | ''liquid'' (default vapor); the PFR is single-phase
      and a two-phase state anywhere along the profile is refused'
  reaction_set:
    description: inline ReactionSet, or a string id resolved against Flowsheet.reactions
  thermal:
    description: "'isothermal' | 'adiabatic' | {duty_W: W} | {coolant_T_K: K, U_W_m2K:\n\
      \  W/(m2 K)} (coolant branch integrates q_V = U\xB7(4/Dt)\xB7(T_c - T), spec\
      \ equation 7)"
  tube_diameter_m:
    description: tube inner diameter Dt, m (> 0); wall area per unit tube volume is
      4/Dt
    type: number
  viscosity_Pa_s:
    description: "mixture viscosity for the Ergun equation \u2014 required when a\
      \ bed is given and the thermo package exposes no transport properties"
    type: number
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-F 6

> R1 implemented (U-R2); single phase, no pressure drop. V1 gap — no transcribable printed validation case: searches 'Fogler Elements of Chemical Reaction Engineering PFR example first order irreversible gas phase numerical conversion worked example printed values' and 'Example 4- Fogler PFR gas phase 500 K volume final conversion table printed' found only umich web self-test pages and a 4th-ed chapter PDF snippet, none with a full feed/kinetics/outlet state reproducible without reconstruction
