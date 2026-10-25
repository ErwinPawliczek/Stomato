# Membrane (gas) (`membrane`)

Family: **separation** · P&ID symbol: `M`

Rigour ladder: R0 provisional, R1 provisional, R2 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed_in` | yes | high-pressure feed gas |
| outlet | `permeate` | yes | permeate stream |
| outlet | `residue` | yes | residue stream |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.separation.membrane:Membrane` | exactly one of permeate_recovery (any components) and stage_cut with perm_ratio (binary Weller-Steiner complete mixing); the permeate leaves at P_permeate, the residue at P_in. Evidence gap — the stage-cut model is validated against Geankoplis Ex. 13.4-2 (air, y_O2 = 0.5068, reject x_O2 = 0.1345); the permeate_recovery path is a spec split with V0 self-consistency only. |
| R1 | provisional | `ngdesign.units.separation.membrane_r1:MembraneR1` | solution-diffusion with permeances, cross-flow (Weller-Steiner 1950, Pan 1983) with the local permeate y_i = J_i/ΣJ from a bracketed brentq (closed form at P_l = 0) and the feed side dn_i/da = -J_i integrated DOP853 at rtol 1e-11; stage-cut mode by a terminal event with the A_hard cap; isothermal outlets via split_by_component as in R0. |
| R2 | provisional | `ngdesign.units.separation.membrane_r2:MembraneR2` | counter-current module, Pan 1983 shooting on the residue flows (scipy root hybr, tol 1e-12) with the permeate plug flow dp_i/da = -J_i toward the feed end, the M2 switch at Sum(p) <= 1e-12 F, and design mode by brentq on theta_R2(A) - theta over [0, A_R1(theta)]; outlets as in R0/R1. |

### R0 parameters

```yaml
properties:
  P_permeate:
    description: permeate-side absolute pressure, Pa; required
    type: number
  perm_ratio:
    description: component id to relative permeance; required with stage_cut (binary)
    type: object
  permeate_recovery:
    description: component id to the fraction of its molar flow crossing to the permeate;
      unnamed components stay in the residue
    type: object
  stage_cut:
    description: fraction of the feed molar flow recovered as permeate (binary Weller-Steiner
      model)
    maximum: 1
    minimum: 0
    type: number
type: object
```

### R1 parameters

```yaml
properties:
  P_permeate:
    description: permeate-side absolute pressure, Pa
    exclusiveMinimum: 0
    type: number
  area_m2:
    description: membrane area, m2 (rating mode)
    exclusiveMinimum: 0
    type: number
  permeances_mol_m2_s_Pa:
    description: component id to permeance, mol/(m2 s Pa) (1 GPU = 3.348e-10); every
      feed component required
    type: object
  stage_cut:
    description: target permeate/feed molar ratio (design mode; area is solved)
    exclusiveMaximum: 1
    exclusiveMinimum: 0
    type: number
required:
- permeances_mol_m2_s_Pa
- P_permeate
type: object
```

### R2 parameters

```yaml
properties:
  P_permeate:
    description: permeate-side absolute pressure, Pa
    exclusiveMinimum: 0
    type: number
  area_m2:
    description: membrane area, m2 (rating mode)
    exclusiveMinimum: 0
    type: number
  permeances_mol_m2_s_Pa:
    description: component id to permeance, mol/(m2 s Pa) (1 GPU = 3.348e-10); every
      feed component required
    type: object
  stage_cut:
    description: target permeate/feed molar ratio (design mode; area is solved)
    exclusiveMaximum: 1
    exclusiveMinimum: 0
    type: number
required:
- permeances_mol_m2_s_Pa
- P_permeate
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-membrane-geankoplis-13-4-2` | R0 | `outlet.permeate.composition.O2` | 0.5068 | 0.506809 | abs 0.0001 | pass |
| `V1-membrane-geankoplis-13-4-2` | R0 | `outlet.residue.composition.O2` | 0.1345 | 0.134548 | abs 0.0001 | pass |

- `V1-membrane-geankoplis-13-4-2`: Geankoplis, "Transport Processes and Separation Process Principles", 4th ed., Example 13.4-2 "Membrane Design for Separation of Air" (p. 767): an air feed (z_O2 = 0.209) at 190 cmHg with the permeate side at 19 cmHg (pressure ratio 10), alpha = 10 (O2 permeability / N2 permeability) and stage cut theta = 0.2 give a permeate y_O2 = 0.5068 and a reject x_O2 = 0.1345 by the Weller-Steiner complete-mixing model. Numbers read from the FOSSEE open transcription of Geankoplis Ch. 13 (tbc-python.fossee.in, GeankoplisChapter13, Example 13.4-2). The compositions come from the complete-mixing algebra alone (thermo only sets the outlet states), so no equation-of-state gap applies; the tolerances are the book's four-decimal rounding.

## References

- docs/unit-catalogue-plan.md §2 U-D 8

> R0 split and stage-cut specs implemented; Geankoplis Ex. 13.4-2 example.
