# 2-phase separator / KO drum (`scrubber`)

Family: **separation** · P&ID symbol: `V`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | two-phase feed |
| outlet | `gas_out` | yes | vapour outlet |
| outlet | `liquid_out` | yes | liquid outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.separator:Scrubber` | PT/PH/PVF flash with ΔP; gas and liquid leave at their flash states |
| R1 | provisional | `ngdesign.units.separation.scrubber_r1:ScrubberR1` | Souders-Brown sizing (York demister K) and droplet carry-over at a given diameter; reduces to R0 without diameter_m or at E = 0 |

Sizer plugin: `scrubber`

### R1 parameters

```yaml
properties:
  K_m_s:
    description: Souders-Brown K, m/s; default York demister fit at the drum pressure
    exclusiveMinimum: 0
    type: number
  dP:
    description: pressure drop, Pa; default 0 (R0)
    minimum: 0
    type: number
  diameter_m:
    description: vessel inside diameter, m; enables the carry-over calculation
    exclusiveMinimum: 0
    type: number
  droplet_d_rr_m:
    description: Rosin-Rammler characteristic droplet size, m
    exclusiveMinimum: 0
    type: number
  droplet_n_rr:
    description: Rosin-Rammler spread parameter
    exclusiveMinimum: 0
    type: number
  gas_viscosity_Pa_s:
    description: gas viscosity override, Pa s
    exclusiveMinimum: 0
    type: number
  inlet_entrained_fraction:
    description: fraction of the liquid entering the gravity section as droplets
    maximum: 1
    minimum: 0
    type: number
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-scrubber-gpsa-7-2` | R1 | `info.Q_gas_m3_s` | 1.61228 | 1.61228 | abs 0.00015 | pass |
| `V1-scrubber-gpsa-7-2` | R1 | `info.v_max_m_s` | 0.459451 | 0.433763 | abs 0.0015 | assessed miss |
| `V1-scrubber-gpsa-7-2` | R1 | `info.D_min_m` | 2.11376 | 2.17545 | abs 0.0016 | assessed miss |

- `V1-scrubber-gpsa-7-2`: GPSA Engineering Data Book, 13th ed. (FPS), Section 7, Example 7-2, transcribed from the publisher's official calculation workbook (gpamidstream.org, DBCalculations-13thEdition-Section7.xlsx, "Example 7-2" sheet): a vertical gas-liquid separator with a high-efficiency wire-mesh mist eliminator handling 150 MMSCFD gas (MW 17.55) and 100 gpm condensate at 120 degF, 500 psig, with a 10% design factor; rho_g = 1.552 lb/ft3, rho_l = 44.68 lb/ft3; QA = 56.94 ft3/s; K = 0.35 ft/s corrected by Fig. 7-36 to K = 0.28595 ft/s; Vmax = 1.51 ft/s (Equation 7-11); D = 6.93 ft + 0.33 ft support ring = 7.26 ft, selected 7.5 ft. The SI edition's example number is not verified; the transcription anchors on the 13th-edition FPS workbook sheet. The case folds the 10% design factor and GPSA's two streams into one feed: the overall composition (C1/C2/nC7/nC8/nC10) and the 3258 mol/s total are chosen so the flashed vapor reproduces QA at the drum conditions, and K_m_s is the printed corrected K.
  - assessed: Measured miss (PR package, this case's feeds and params): Q_gas_m3_s = 1.612284, matching the printed QA conversion to 7 digits. v_max = 0.433763 m/s, 5.6% below the printed 0.459451 m/s, and D_min = 2.175451 m, 2.9% above the printed 2.113765 m. Cause: GPSA gives rho_g and rho_l as independent stream properties, while the unit derives both from one feed flash. The flashed vapor reads 24.680 kg/m3 (0.7% below the printed 1.552 lb/ft3 = 24.861 kg/m3), and the flashed liquid — condensate in equilibrium with 500-psig gas — dissolves about 14 mol% C1 and reads 635.96 kg/m3, 11% below the printed 44.68 lb/ft3 = 715.70 kg/m3; no single-feed composition reproduces both printed densities at once. The density miss propagates through the Souders-Brown chain (v_max carries sqrt((rho_l - rho_g)/rho_g)). The tolerances are the workbook's display rounding of the 3-4 significant-figure prints, kept unabsorbed; the miss is the model gap, reported here. As an independent cross-check, the York demister fit at the drum pressure (514.7 psia) gives 0.286417 ft/s, 0.16% above the workbook's Fig. 7-36 correction of 0.28595 ft/s.

## References

- docs/unit-catalogue-plan.md §2 U-D 1

> the registered id stays `scrubber` (historical); the row is the palette's 2-phase separator.
