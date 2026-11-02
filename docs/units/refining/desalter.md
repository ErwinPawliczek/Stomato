# Desalter (`desalter`)

Family: **refining** · P&ID symbol: `DS`

Rigour ladder: R0 provisional, R1 provisional

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
| R1 | provisional | `ngdesign.units.refining.desalter_r1:DesalterR1` | Stokes cut (counter-current settling) plus Rosin-Rammler two-population carryover; splits fed to R0. Temperature effect via user-supplied properties (spec option B) |

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

### R1 parameters

```yaml
properties:
  T:
    description: desalter temperature (K), isothermal
    type: number
  d50_fine_um:
    description: volume-median drop diameter of the uncontacted emulsion, micrometre
    exclusiveMinimum: 0
    type: number
  d50_mixed_um:
    description: volume-median drop diameter of the coalesced wash and brine water,
      micrometre
    exclusiveMinimum: 0
    type: number
  dP:
    description: pressure drop from the crude inlet (Pa, default 0)
    type: number
  mixing_efficiency:
    description: fraction of the crude brine contacted by the wash water
    maximum: 1
    minimum: 0
    type: number
  mu_oil_Pa_s:
    description: oil viscosity at T, Pa s
    exclusiveMinimum: 0
    type: number
  rho_oil_kg_m3:
    description: oil density at T, kg/m3
    exclusiveMinimum: 0
    type: number
  rho_water_kg_m3:
    description: water density at T, kg/m3
    exclusiveMinimum: 0
    type: number
  rosin_rammler_n:
    description: Rosin-Rammler spread exponent of both populations
    exclusiveMinimum: 0
    type: number
  settling_area_m2:
    description: horizontal area the oil rises through, m2
    exclusiveMinimum: 0
    type: number
required:
- T
- settling_area_m2
- d50_mixed_um
- d50_fine_um
- rosin_rammler_n
- mixing_efficiency
- rho_oil_kg_m3
- rho_water_kg_m3
- mu_oil_Pa_s
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-H 2

> R1 takes oil and water densities and oil viscosity as required params (spec option B): no package gives honest values for a pseudo crude. V1 gap - provisional without a case. Searched PetroWiki 'Desalting' and Wauquier (Petroleum Refining vol. 1, crude desalting): both state a 0.1-0.2 vol% BS&W specification but print no worked case, so the former V2102 pin (which echoed its own input spec and the adapter's default salt removal) was withdrawn at re-review. The water/salt/BS&W split is covered by closed-form tests in tests/units/refining/test_separation.py.
