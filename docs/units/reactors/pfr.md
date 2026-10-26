# Plug-flow reactor (`pfr`)

Family: **reactors** · P&ID symbol: `R`

Rigour ladder: R1 provisional, R2 planned, R3 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `outlet` | yes | reactor effluent |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R1 | provisional | `ngdesign.units.reactors.pfr:PfrR1` | kinetic extents integrated over V (BDF, depletion and pressure-floor events); the RHS never flashes — single-phase properties come from phase_props and the audit flashes once per output point, so the flash count is O(n_output) and independent of V (P0-06); the outlet closes exactly on the formation-enthalpy basis and info carries extents, T_profile_out_K, T_closure_gap_K, T_max_K, V_at_T_max_m3. The energy ODE uses the closure-consistent dH (PR #311 review, blocking items 1 and B: heat_of_reaction at 298.15 K plus stoichiometric partial molar enthalpies of the actual mixture, from a finite difference of the mixture enthalpy flow); the residual T_closure_gap_K measures 6.6e-7 K on ideal-raoult for the nC4 isomerisation case, within the spec's 1e-3 K consistency bound |
| R2 | planned | — | integrated along length with heat transfer and pressure drop (Ergun) on the shared integrator (ngdesign.units.reactors.plug_flow) |
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

## References

- docs/unit-catalogue-plan.md §2 U-F 6

> R1 implemented (U-R2); single phase, no pressure drop. V1 gap — no transcribable printed validation case: searches 'Fogler Elements of Chemical Reaction Engineering PFR example first order irreversible gas phase numerical conversion worked example printed values' and 'Example 4- Fogler PFR gas phase 500 K volume final conversion table printed' found only umich web self-test pages and a 4th-ed chapter PDF snippet, none with a full feed/kinetics/outlet state reproducible without reconstruction
