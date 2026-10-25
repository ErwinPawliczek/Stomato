# Decanter (`decanter`)

Family: **separation** · P&ID symbol: `V`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | LLE feed |
| outlet | `light_out` | yes | light liquid phase |
| outlet | `heavy_out` | yes | heavy liquid phase |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.separation.decanter:Decanter` | PT flash at (T_in, P_in - dP); the two liquid phases leave light/heavy by phase density; a single-liquid or vapour-returning flash is refused, naming T and P. Evidence gap — V0 self-consistency only — no cited worked example validates a decanter split at R0 |
| R1 | provisional | `ngdesign.units.separation.decanter_r1:DecanterR1` | Stokes settling with Richardson-Zaki hindered settling on the R0 split; Hazen ideal-settler efficiency scales the dispersed outlet and reflashes the continuous outlet with the entrained dispersed liquid; Re_t >= 1 is refused (R1 is a Stokes model) |

### R0 parameters

```yaml
properties:
  dP:
    description: pressure drop, Pa; default 0
    minimum: 0
    type: number
type: object
```

### R1 parameters

```yaml
properties:
  continuous_viscosity_Pa_s:
    description: continuous-phase viscosity override, Pa s
    exclusiveMinimum: 0
    type: number
  dP:
    description: pressure drop, Pa; default 0
    minimum: 0
    type: number
  diameter_m:
    description: horizontal vessel diameter, m (interface at the centre line)
    exclusiveMinimum: 0
    type: number
  dispersed_phase:
    description: phase forming the droplets
    enum:
    - light
    - heavy
    type: string
  droplet_diameter_m:
    description: design droplet diameter, m
    exclusiveMinimum: 0
    type: number
  interface_area_m2:
    description: interface (settling) area, m2
    exclusiveMinimum: 0
    type: number
  length_m:
    description: horizontal vessel length, m
    exclusiveMinimum: 0
    type: number
required:
- dispersed_phase
- droplet_diameter_m
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-decanter-sinnott-10-3` | R1 | `info.u_t_m_s` | 0.0012 | 0.00252101 | abs 5e-05 | assessed miss |

- `V1-decanter-sinnott-10-3`: Sinnott, "Coulson & Richardson's Chemical Engineering" Vol. 6, 4th ed., Example 10.3 (decanter to separate a light oil from water, oil dispersed): oil 1000 kg/h at 900 kg/m3 and 3 mN s/m2, water 5000 kg/h at 1000 kg/m3 and 1 mN s/m2, design droplet diameter 150e-6 m; printed Stokes droplet velocity 0.0012 m/s and required interfacial area 1.16 m2. The comparable quantity the unit reports is info.u_t_m_s (the book's settling velocity step). The book's densities cannot be passed to the unit (no density override param), so the anchor is expected to miss for equation-of-state reasons; the miss is recorded in `assessed` per the spec, and the level's validation field stays unset because the case does not pass.
  - assessed: Measured miss (pr package, this case's feeds and params): u_t = 2.521e-3 m/s, 2.10x the book's printed 0.0012 m/s. Cause: the unit takes the two liquid densities from the flashed pr phases (aqueous 851.4, hc-liquid 645.7 kg/m3 at 293.15 K, 1 bar), so the driving gap is 205.7 kg/m3 versus the book's 900/1000 (gap 100); with the book's water viscosity passed through continuous_viscosity_Pa_s the Stokes step scales with that gap. The book's oil is a generic 900 kg/m3 oil that a pure-component pr feed cannot reproduce. Secondary difference: on this feed the dispersed phase holds 84.3 % of the two-liquid volume (the book's oil is the minor phase), so the Richardson-Zaki correction (n = 4.552 at Re_t = 0.322) and the Hazen efficiency (6.1e-4 at the book's required 1.16 m2) sit far from the book's design point; the settling velocity is the comparable anchor. The tolerance is the book's two-significant-digit print of 0.0012 m/s. The level's validation field stays unset because the case does not pass.

## References

- docs/unit-catalogue-plan.md §2 U-D 4

> R0 LLE split implemented; Stokes settling sizing is R1 (plan §2b).
