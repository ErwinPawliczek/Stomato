# Plug-flow reactor (`pfr`)

Family: **reactors** · P&ID symbol: `R`

Rigour ladder: R1 validated, R2 provisional, R3 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `outlet` | yes | reactor effluent |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R1 | validated | `ngdesign.units.reactors.pfr:PfrR1` | kinetic extents integrated over V (BDF, depletion and pressure-floor events); the RHS never flashes — single-phase properties come from phase_props and the audit flashes once per output point, so the flash count is O(n_output) and independent of V (P0-06); the outlet closes exactly on the formation-enthalpy basis and info carries extents, T_profile_out_K, T_closure_gap_K, T_max_K, V_at_T_max_m3. The energy ODE uses the closure-consistent dH (PR #311 review, blocking items 1 and B: heat_of_reaction at 298.15 K plus stoichiometric partial molar enthalpies of the actual mixture, from a finite difference of the mixture enthalpy flow); the residual T_closure_gap_K measures 6.6e-7 K on ideal-raoult for the nC4 isomerisation case, within the spec's 1e-3 K consistency bound |
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

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-FOGLER-EO-PBR-NODP` | R1 | `info.extent_eo_mol_s` | 0.0816466 | 0.0816413 | abs 7.35e-05 | pass |
| `V1-FOGLER-EO-PBR` | R2 | `info.extent_eo_mol_s` | 0.0816466 | 0.0813953 | abs 4.05e-05 | assessed miss |

- `V1-FOGLER-EO-PBR-NODP`: Fogler, Elements of Chemical Reaction Engineering, 4th ed., Prentice Hall 2006, Example 4-6, p. 195 eq. (E4-6.17): 35.3 lb of catalyst per tube for 60 % conversion neglecting pressure drop (k' = 0.0266 lbmol/(h lb cat), eq. E4-6.11; F_A0 = 1.08 lbmol/h per tube); scan read 2026-11-04 at https://archive.org/details/elementsofchemicalreactionengineering4thed
- `V1-FOGLER-EO-PBR`: Fogler, Elements of Chemical Reaction Engineering, 4th ed., Prentice Hall 2006, Example 4-6, pp. 191-195: '60% conversion is achieved with 44.5-lb catalyst in each tube' (p. 195), with the Ergun parameters of Example 4-4, pp. 183-184 (A_c 0.01414 ft2, D_p 0.0208 ft, voidage 0.45, mu 0.0673 lbm/(ft h)); scan read 2026-11-04 at https://archive.org/details/elementsofchemicalreactionengineering4thed
  - assessed: Measured extent 0.0813953 mol/s (X = 0.59815) vs the printed 60 % at 44.5 lb (0.0816466 mol/s, +-4.05e-5): a miss of -2.5e-4 mol/s (X -1.85e-3). Measured outlet P 5.4715 bar (y = 0.540) vs the book's y = 0.550 at that weight. Cause investigated: the book takes the gas as air (rho_0 = 0.413 lbm/ft3, Ex. 4-4) and so fixes alpha = 0.0166 /lb; the model's Ergun term uses the actual feed density, ideal gas at M = 28.615 g/mol: 6.5406 kg/m3 = 0.4083 lbm/ft3, 1.15 % below the book's air value. Both Ergun terms scale with 1/rho_0, so alpha is ~1.15 % larger, the pressure falls faster and the rate (proportional to P) is lower. A stated simplification of the source (air properties), not a model bug: the same kinetics without the bed (V1-FOGLER-EO-PBR-NODP, R1) reproduce the book. Not tuned away (the model has no density override, and adding one only to match would be fitting).

## References

- docs/unit-catalogue-plan.md §2 U-F 6

> R1 validated on Fogler 4th ed. Example 4-6 without pressure drop (V1-FOGLER-EO-PBR-NODP, 35.3 lb catalyst for X = 0.60, read 2026-11-04). R2 runs the same example with the Ergun bed (V1-FOGLER-EO-PBR) and misses by X -1.85e-3 because the book takes the gas as air (rho_0 1.15 % above the actual feed); recorded, R2 stays provisional. R1, R2 and R3 implemented; single phase. R2 and R3 ship provisional on the spec's hand calculations (Fogler eq. 4-33 Ergun, wall-exchange exponential, Thiele/activity closed form) and the reductions to the lower level; R3 V1 search 2026-11-04: Fogler 4th ed. Ex. 12-3 gives only Thiele moduli (no k or De) and Ex. 12-4 needs the overall effectiveness with external mass transfer (Thoenes-Kramers), which R3 does not model; note R3's shape-normalized tanh(phi/3)/(phi/3) gives 0.910 at the sphere modulus 1.65 where the exact sphere 3(phi coth phi - 1)/phi^2 gives 0.856 (at 16.5: 0.182 vs exact 0.171, the book printing 0.182 from the large-phi limit 3/phi); no V1 case was attempted for them. R1 V1 gap — no transcribable printed validation case: searches 'Fogler Elements of Chemical Reaction Engineering PFR example first order irreversible gas phase numerical conversion worked example printed values' and 'Example 4- Fogler PFR gas phase 500 K volume final conversion table printed' found only umich web self-test pages and a 4th-ed chapter PDF snippet, none with a full feed/kinetics/outlet state reproducible without reconstruction
