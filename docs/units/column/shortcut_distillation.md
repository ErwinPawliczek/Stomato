# Shortcut distillation (FUG) (`shortcut_distillation`)

Family: **column** · P&ID symbol: `T`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed` | yes | column feed |
| outlet | `distillate` | yes | light-key product |
| outlet | `bottoms` | yes | heavy-key product |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.column_shortcut.distillation:ShortcutDistillation` | Fenske-Underwood-Gilliland with Kirkbride feed stage (Seader-Henley V1 oracle); saturation K-values at product states, two-phase feed q from the inlet flash |

### R0 parameters

```yaml
properties:
  P_bottom:
    description: bottom-stage pressure, Pa (default P_top)
    type: number
  P_top:
    description: top-stage pressure, Pa (default feed pressure)
    type: number
  R:
    description: reflux ratio (give R or R_over_Rmin)
    type: number
  R_over_Rmin:
    description: reflux ratio as multiple of the Underwood Rmin
    type: number
  condenser:
    description: total | partial (default total)
    type: string
  heavy_key:
    description: heavy-key component id
    type: string
  light_key:
    description: light-key component id
    type: string
  recovery_HK_B:
    description: fraction of the heavy key in the bottoms (default 1)
    type: number
  recovery_LK_D:
    description: fraction of the light key in the distillate (default 1)
    type: number
required:
- light_key
- heavy_key
- R_over_Rmin
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-fug-debutanizer-seader97` | R0 | `info.kirkbride_ratio` | 0.445 | 0.445938 | rel 0.01 | pass |
| `V1-fug-debutanizer-seader97` | R0 | `info.Nmin` | 8.88 | 7.93401 | abs 0.005 | assessed miss |
| `V1-fug-debutanizer-seader97` | R0 | `info.Rmin` | 0.479 | 0.34301 | abs 0.0005 | assessed miss |

- `V1-fug-debutanizer-seader97`: Seader, Henley & Roper, 3rd ed., Examples 9.2-9.7, pp. 350-360: debutanizer, Fenske Nmin = 8.88 and Kirkbride feed-stage ratio 0.445 (verified against the printed correlation and Example 9.2 product split); Underwood Rmin = 0.479.
  - assessed: Measured on the default Peng-Robinson package (after the Underwood bracket fix): Nmin 7.934 vs 8.88 (-10.7 %) and Rmin 0.3430 vs 0.479 (-28.4 %). Cause: Fenske and Underwood consume relative volatilities, and the PR K-ratios at the example's saturation states differ from the book's K-chart estimates; the book's printed K-values for Examples 9.2-9.7 are not carried in-repo (no published value is typed without reading its source), so the case cannot be driven with them this round. The flow-based Kirkbride ratio is unaffected (0.4459 vs 0.445, +0.2 %) and passes at the book's rounding.

## References

- docs/unit-catalogue-plan.md §2 U-E 1

> roadmap; S1 slice needs it (plan §2b). R0 duty approximation: the condenser duty condenses the overhead vapour at the distillate composition (h at its dew T minus h at its bubble T); a real total condenser's vapour carries the top-tray composition, which R0 does not track.
