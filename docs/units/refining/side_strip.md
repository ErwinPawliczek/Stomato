# Side stripper (`side_strip`)

Family: **refining** · P&ID symbol: `SS`

Rigour ladder: R0 provisional, R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `draw_in` | yes | side draw from the main column |
| inlet | `steam_in` | yes | stripping steam |
| outlet | `overhead_out` | yes | stripped product + steam back to the column |
| outlet | `bottoms_out` | yes | stripped liquid product |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.refining.side_strip:SideStrip` | steam-stripped draw, per-pseudo Kremser stripping via units/_physics/shortcut.kremser_fraction (S_i = K_i V/L, K from thermo.k_values at the stripper T, P) (spec U-H1) |
| R2 | planned | — | MESH stage section coupled to the main column |

### R0 parameters

```yaml
properties:
  N:
    description: number of ideal stages in the stripped section
    type: number
  P:
    description: stripper pressure (Pa abs, default the draw_in P)
    type: number
  T:
    description: stripper temperature (K)
    type: number
required:
- T
- N
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-H 4

> roadmap; R0 V1 gap — the Watkins Petroleum Refinery Distillation side-stripper example is not open (access-controlled Scribd copies of the 1969 report; no open reproduction with printed inputs/results found — searched 2026-10-24 across Scribd scans, Colorado School of Mines crude-units lecture notes, Bagajewicz crude-fractionation papers and the BRE refinery-operations manual), so the row ships provisional with the closed-form test tests/units/refining/test_side_strip.py per U-R1 conventions.
