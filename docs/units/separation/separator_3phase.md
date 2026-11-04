# 3-phase separator (`separator_3phase`)

Family: **separation** · P&ID symbol: `V`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | three-phase feed |
| outlet | `gas_out` | yes | vapour outlet |
| outlet | `hc_out` | yes | hydrocarbon liquid outlet |
| outlet | `water_out` | yes | water outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.separator:Separator3Phase` | VLLE flash; gas, hydrocarbon and water leave at their phase states |
| R1 | provisional | `ngdesign.units.separation.separator_3phase_r1:Separator3PhaseR1` | rating at a given geometry (D, L, orientation, NLL/NIL) - Souders-Brown gas capacity and gas-section cut size (report only), oil/water residence times, Stokes cut sizes and liquid-liquid carry-over of given droplets; reduces to R0 without geometry, droplets or entrainment |

Sizer plugin: `separator_3phase`

### R1 parameters

```yaml
properties:
  K_m_s:
    description: Souders-Brown K, m/s; default York demister fit (x1.25 horizontal)
    exclusiveMinimum: 0
    type: number
  dP:
    description: pressure drop, Pa; default 0 (R0)
    minimum: 0
    type: number
  diameter_m:
    description: vessel inside diameter, m; enables the rating
    exclusiveMinimum: 0
    type: number
  gas_viscosity_Pa_s:
    description: gas viscosity, Pa s; used only when the package gives none
    exclusiveMinimum: 0
    type: number
  interface_level_m:
    description: normal interface level (NIL), m above the bottom
    exclusiveMinimum: 0
    type: number
  length_m:
    description: 'effective (seam-to-seam) length, m; vertical: height above the bottom
      seam'
    exclusiveMinimum: 0
    type: number
  liquid_level_m:
    description: normal liquid level (NLL; oil weir crest), m above the bottom
    exclusiveMinimum: 0
    type: number
  oil_droplet_diameter_m:
    description: oil droplet diameter in the water layer, m
    exclusiveMinimum: 0
    type: number
  oil_in_water_fraction:
    description: fraction of the oil entering the water layer as droplets
    maximum: 1
    minimum: 0
    type: number
  oil_viscosity_Pa_s:
    description: oil viscosity, Pa s; used only when the package gives none
    exclusiveMinimum: 0
    type: number
  orientation:
    description: vessel orientation; default horizontal
    enum:
    - horizontal
    - vertical
    type: string
  water_droplet_diameter_m:
    description: water droplet diameter in the oil pad, m
    exclusiveMinimum: 0
    type: number
  water_in_oil_fraction:
    description: fraction of the water entering the oil pad as droplets
    maximum: 1
    minimum: 0
    type: number
  water_viscosity_Pa_s:
    description: water viscosity, Pa s; used only when the package gives none
    exclusiveMinimum: 0
    type: number
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-D 2

> R1 V1 gap: no printed worked example with printed inputs and results could be verified. Searched Arnold & Stewart, Surface Production Operations Vol. 1 (horizontal three-phase example; no accessible copy), PetroWiki "Separator sizing" (now redirects to a OnePetro landing page), GPSA Engineering Data Book Sect. 7 (no accessible copy), and the web for a horizontal three-phase worked example (only unattributed slide/Scribd copies). Those examples print SG and viscosity in field units, which R1 takes from the thermo package, so a V1 case also needs a feed reproducing the printed SGs.
