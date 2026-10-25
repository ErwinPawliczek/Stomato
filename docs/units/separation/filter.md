# Filter (`filter`)

Family: **separation** · P&ID symbol: `FLT`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | slurry feed |
| outlet | `filtrate` | yes | clear filtrate |
| outlet | `cake` | yes | solids cake |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.separation.filter:Filter` | per-component split spec — the cake split is the spec, not a correlation constant; the filtrate leaves at P_in - dP, the cake at P_in. Evidence gap — cake-resistance physics is R1, so no worked example validates a cake at R0 (V0 self-consistency only). |
| R1 | provisional | `ngdesign.units.separation.filter_r1:FilterR1` | Ruth constant-pressure cake filtration over the R0 split — required area, cake thickness and cake moisture (F1-F7); reduces exactly to R0 at zero porosity. |

### R0 parameters

```yaml
properties:
  cake_fractions:
    description: component id to the fraction of its molar flow sent to the cake;
      unnamed components pass entirely to the filtrate
    type: object
  dP:
    description: pressure drop, Pa; applied to the filtrate outlet (the cake leaves
      at the inlet pressure)
    minimum: 0
    type: number
type: object
```

### R1 parameters

```yaml
properties:
  area_m2:
    description: installed filter area, m2 (capacity ratio)
    exclusiveMinimum: 0
    type: number
  cake_fractions:
    description: component id to the fraction of its molar flow sent to the cake (the
      solids)
    type: object
  cake_porosity:
    description: cake void fraction; default 0 (dry cake)
    exclusiveMaximum: 1
    minimum: 0
    type: number
  dP:
    description: filtration pressure difference, Pa; applied to the filtrate
    exclusiveMinimum: 0
    type: number
  filtrate_viscosity_Pa_s:
    description: filtrate viscosity override, Pa s
    exclusiveMinimum: 0
    type: number
  medium_resistance_1_m:
    description: filter medium resistance Rm, 1/m; default 0
    minimum: 0
    type: number
  solid_density_kg_m3:
    description: true solid density, kg/m3
    exclusiveMinimum: 0
    type: number
  specific_cake_resistance_m_kg:
    description: specific cake resistance alpha, m/kg
    exclusiveMinimum: 0
    type: number
  t_down_s:
    description: washing/discharge downtime per cycle, s; default 0
    minimum: 0
    type: number
  t_filtration_s:
    description: filtration time per cycle, s
    exclusiveMinimum: 0
    type: number
required:
- cake_fractions
- dP
- specific_cake_resistance_m_kg
- t_filtration_s
- solid_density_kg_m3
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-D 7

> R1 V1 gap (PR 280) — provisional without a case. Searched the spec's candidates and none prints a case for the batch constant-pressure Ruth model with printed inputs only — Geankoplis 4th ed. sect. 14.2, Examples 14.2-1 and 14.2-2 evaluate alpha and Rm by regression on t-V data, so there is no printed input/output pair to pin at the closed form, and Example 14.2-4 folds the wet-cake moisture into Cs = rho*Cx/(1 - m*Cx) with m = 2 kg wet cake per kg dry cake, a moisture model different from R1's porosity-based cake, so reproducing its printed 6.66 m2 needs an unprinted cake porosity; the FOSSEE open transcription of Geankoplis ch. 14, whose regression prints differ from the book's graphical reads (264.61 s vs the book's 269.7 s recovery time used in 14.2-3); and McCabe, Smith and Harriott 7th ed., Mechanical Separations (fetched and inspected), Example 30.2 being a least-squares regression of t-V data for alpha and Rm and Example 30.3 a continuous rotary-drum design with a compressible cake (alpha = alpha0/dP**0.26) and the moisture folded into the slurry concentration. The level is covered by the closed-form CF1-CF4 tests and the R0-reduction identity instead.
