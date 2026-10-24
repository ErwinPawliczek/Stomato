# Liquid-liquid extractor (`liquid_liquid_extractor`)

Family: **column** · P&ID symbol: `X`

Rigour ladder: R0 provisional, R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed` | yes | feed (raffinate phase) |
| inlet | `solvent_in` | yes | extracting solvent |
| outlet | `extract` | yes | extract phase |
| outlet | `raffinate` | yes | raffinate phase |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.column_shortcut.extractor:LiquidLiquidExtractor` | stage count from Kremser; nonsolutes immiscible at R0 (each stays with its inlet phase) |
| R2 | planned | — | MESH with LLE stages |

### R0 parameters

```yaml
properties:
  K_D:
    description: '{cid: distribution coefficient}; omitted = thermo k_values, refused
      when no second liquid phase'
    type: object
  N:
    description: ideal stages, positive
    type: number
required:
- N
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-kremser-extractor-seader52` | R0 | `info.extraction_fraction_p-dioxane` | 0.891 | 0.890779 | abs 0.001 | pass |

- `V1-kremser-extractor-seader52`: Seader, Henley & Roper, 3rd ed., Example 5.2, pp. 183-185: p-dioxane extracted from water by benzene, countercurrent cascade with the constant-distribution-coefficient basis K'D = 1.2 (mass ratios) and carrier ratio S/FA = 2.0, so E = 2.4; two stages give 89.1 % extraction.

## References

- docs/unit-catalogue-plan.md §2 U-E 9

> roadmap.
