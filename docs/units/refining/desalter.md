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

## References

- docs/unit-catalogue-plan.md §2 U-H 2

> V1 gap - provisional without a case. Searched PetroWiki 'Desalting' and Wauquier (Petroleum Refining vol. 1, crude desalting): both state a 0.1-0.2 vol% BS&W specification but print no worked case, so the former V2102 pin (which echoed its own input spec and the adapter's default salt removal) was withdrawn at re-review. The water/salt/BS&W split is covered by closed-form tests in tests/units/refining/test_separation.py.
