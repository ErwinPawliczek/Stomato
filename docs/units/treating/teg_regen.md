# TEG regenerator + stripping gas (`teg_regen`)

Family: **treating** · P&ID symbol: `T`

Rigour ladder: R0 provisional, R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `rich_in` | yes | rich glycol |
| inlet | `stripping_gas_in` | no | stripping gas |
| outlet | `water_out` | yes | stripped water |
| outlet | `lean_out` | yes | regenerated glycol |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.treating.teg_regen:TEGRegen` | shortcut water split; lean purity on the TEG-water boiling line (teg_activity owner), stripping gas refused at R0 (uncited); info["activity_extrapolated"] flags reboilers outside the Parrish-Won-Baltatu 300-380 K fit range; V1 miss assessed — measured 99.27 wt% vs the GPSA 98.8 wt% read (activity correlation extrapolated past its fitted range), so the level stays provisional until the purity model is defensible at reboiler conditions |
| R2 | planned | — | staged — S1 slice (plan §2b) |

### R0 parameters

```yaml
properties:
  P:
    Pa abs: null
    description: regenerator pressure
    type: number
  T_reboiler:
    K: null
    description: reboiler temperature
    type: number
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1201-teg-regen-gpsa` | R0 | `info.lean_teg_mass_fraction` | 0.988 | 0.992655 | abs 0.0015 | assessed miss |

- `V1201-teg-regen-gpsa`: GPSA Engineering Data Book, 14th ed., Sect. 20 regeneration example (Ex. 20-12 basis: rich TEG 97.5 wt% at 300 F; Ex. 20-11 Fig. 20-56 read: 98.8 wt% lean TEG at a 400 F reboiler, no stripping gas). 400 F reboiler = 477.594 K exactly, not the 477.15 K first assumed.
  - assessed: Measured 0.99265 wt-fraction lean TEG (99.27 wt%) at the GPSA basis (400 F reboiler, 1 atm): 0.47 wt% above the Fig. 20-56 read of 98.8 wt%. The Parrish-Won-Baltatu water-activity correlation behind ngdesign.units.teg_activity was fitted over 300-380 K; the 400 F reboiler sits far outside the fit and the unit now flags this in info["activity_extrapolated"] (= 1.0 here), so the shortcut over-purifies by ~0.5 wt% absolute. The miss is documented here instead of widening the tolerance; the model reports the ideal-limit purity it can defend at R0. Published cross-checks put the 400 F no-stripping-gas value at 98.7-98.8 wt% (Moshfeghian, Campbell Tip of the Month, May 2013), consistent with the GPSA figure.

## References

- docs/unit-catalogue-plan.md §2 U-G 4

> roadmap.
