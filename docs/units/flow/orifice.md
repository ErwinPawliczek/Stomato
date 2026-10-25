# Orifice / flow element (`orifice`)

Family: **flow** · P&ID symbol: `FE`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | element inlet |
| outlet | `outlet` | yes | element outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.flow.orifice:Orifice` | ΔP from a discharge coefficient |
| R1 | provisional | `ngdesign.units.flow.orifice_r1:OrificeR1` | ISO 5167-2 RHG C, expansibility, permanent loss; rating and sizing |

### R1 parameters

```yaml
properties:
  C_specified:
    description: fixed discharge coefficient instead of Reader-Harris/Gallagher
    type: number
  D_m:
    description: 'pipe internal diameter, m (ISO 5167-2: 0.05 to 1.0)'
    type: number
  bore_m:
    description: 'rating mode: orifice bore, m (>= 12.5 mm, beta in [0.1, 0.75])'
    type: number
  dP_design_Pa:
    description: 'sizing mode: differential pressure at the stream flow, Pa'
    type: number
  mu_Pa_s:
    description: viscosity override, Pa.s
    type: number
  taps:
    description: tap arrangement, default flange
    enum:
    - corner
    - flange
    - D-D/2
    type: string
required:
- D_m
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-B 9

> R0 fixed-Cd dP read; R1 ISO 5167-2 RHG C, expansibility and permanent loss (rating and sizing). V1 gap - ISO 5167 has no normative worked example; the spec's candidates (API MPMS Ch. 14.3 Part 4 / AGA Report No. 3 Part 4 1992 and 2019, Miller 3rd ed., Reader-Harris 2015) were searched 2026-10-25 - only front-matter sample PDFs openly accessible (the AGA Part 4 sample carries no example numbers), the books paywalled, so no printed inputs-plus-results case could be transcribed.
