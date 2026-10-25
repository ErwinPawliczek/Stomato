# Hydrate check / inhibitor injection (`hydrate_check`)

Family: **separation** · P&ID symbol: `HC`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | gas stream at risk of hydrates |
| inlet | `inhibitor_in` | no | inhibitor (MeOH/MEG) injection |
| outlet | `outlet` | yes | gas with hydrate margin and inhibitor dose reported |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.separation.hydrate_check:HydrateCheck` | adiabatic PH mix; hydrate_T from hammerschmidt_formation at the mixed P, dose from nielsen_bucklin_suppression at the operating T; the required inhibitor rate covers the aqueous phase only — GPSA's vapour and hydrocarbon-liquid methanol losses are excluded at R0 |
| R1 | planned | — | Katz / van der Waals-Platteeuw (via thermo) |

### R0 parameters

```yaml
properties:
  P:
    description: mixed outlet pressure, Pa abs; default min inlet P
    type: number
  T_operating_K:
    description: target operating temperature, K; drives the required-inhibitor-dose
      info
    type: number
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-hydrate-gpsa-20-10` | R0 | `info.required_inhibitor_mass_fraction` | 0.275 | 0.276358 | abs 0.005 | pass |

- `V1-hydrate-gpsa-20-10`: GPSA Engineering Data Book (SI), Sect. 20, Example 20-10 with the 2004 SI errata (K_H,MeOH = 1297; Hammerschmidt not to be used beyond 20-25 wt% MeOH, Nielsen-Bucklin preferred): a 14 degC hydrate-temperature depression needs 27.5 wt% MeOH in the free-water phase (Hammerschmidt gives 25.5). The case fixes T_operating_K at hydrate_T - 14.0 K (hydrate_T from the catalogue hammerschmidt_formation at the case pressure) so the required aqueous mass fraction reproduces exactly that scenario. The feed carries 15 % water and a 1.5 mol/s methanol trim so the PR package returns a distinct water-rich liquid phase at the target T; the dose anchor itself is correlation-only (the required fraction comes from the Nielsen-Bucklin bisection).

## References

- docs/unit-catalogue-plan.md §2 U-D 10

> roadmap; S2 slice (plan §2b).
