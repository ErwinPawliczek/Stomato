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
| R1 | provisional | `ngdesign.units.reactors.pfr:PfrR1` | kinetic extents integrated over V (BDF, depletion and pressure-floor events); the RHS never flashes — single-phase properties come from phase_props and the audit flashes once per output point, so the flash count is O(n_output) and independent of V (P0-06); the outlet closes exactly on the formation-enthalpy basis and info carries extents, T_profile_out_K, T_closure_gap_K, T_max_K, V_at_T_max_m3. KNOWN GAP — the spec's |T_closure_gap_K| < 1e-3 K bound is not met on ideal-raoult (measured 1.4e-2 K for the nC4 isomerisation case): the package's sensible enthalpy differs from the formation- databank Cp integral by ~0.6 % over the reaction span, a property-package inconsistency, not an integrator error (the isothermal case and the V0 balance close at 1e-8); the test asserts 0.05 K and the spec tolerance is raised for review (SPEC ISSUE on the PR) |
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

> R1 implemented (U-R2); single phase, no pressure drop.
