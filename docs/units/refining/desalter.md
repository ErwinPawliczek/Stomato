# Desalter (`desalter`)

Family: **refining** · P&ID symbol: `DS`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `crude_in` | yes | crude feed |
| inlet | `wash_in` | yes | wash water |
| outlet | `crude_out` | yes | desalted crude |
| outlet | `water_out` | yes | salty waste water |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.refining.desalter:Desalter` | water/salt/BS&W split spec, wash-water mix (spec U-H1, component split at isothermal T with ΔP) |
| R1 | planned | — | efficiency vs wash rate and ΔT (cited correlation) |

### R0 parameters

```yaml
properties:
  T:
    description: outlet temperature (K), isothermal desalter
    type: number
  dP:
    description: pressure drop from the crude inlet (Pa, default 0)
    type: number
  salt_removal:
    description: fraction of tracked NaCl leaving with the brine
    type: number
  water_carryover_frac:
    description: fraction of inlet water reporting to the desalted crude (the BS&W)
    type: number
required:
- T
- water_carryover_frac
- salt_removal
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V2102` | R0 | `info.bsw_vol_pct` | 0.2 | 0.203049 | rel 0.02 | pass |
| `V2102` | R0 | `info.salt_removed_frac` | 0.95 | 0.95 | abs 0.001 | pass |

- `V2102`: Desalter BS&W specification 0.2 vol% and 0.5-4 vol% wash-water range: PetroWiki 'Desalting' / Wauquier, Petroleum Refining vol. 1, crude desalting; salt removal 0.95 per the adapter's published-removal default. The BS&W value is the closed-form spec check the adapter implements

## References

- docs/unit-catalogue-plan.md §2 U-H 2

> roadmap.
