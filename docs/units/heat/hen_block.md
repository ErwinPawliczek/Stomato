# Heat exchanger network block (HEN) (`hen_block`)

Family: **heat** · P&ID symbol: `HEN`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `hot_in_1` | yes | first hot stream (0 = inactive) |
| inlet | `hot_in_2` | no | second hot stream (0 = inactive) |
| inlet | `cold_in_1` | yes | first cold stream (0 = inactive) |
| inlet | `cold_in_2` | no | second cold stream (0 = inactive) |
| outlet | `hot_out_1` | yes | positional outlet for hot_in_1 |
| outlet | `hot_out_2` | yes | positional outlet for hot_in_2 |
| outlet | `cold_out_1` | yes | positional outlet for cold_in_1 |
| outlet | `cold_out_2` | yes | positional outlet for cold_in_2 |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.heat.hen_block:HenBlock` | every active stream reaches its T_out target; the Linnhoff problem table (on package-derived or cp_*-overridden CPs) reports utility targets QH_min/QC_min and the pinch (no utilities are added) |

### R0 parameters

```yaml
properties:
  T_out_cold_in_1:
    description: cold_in_1 target, K
    type: number
  T_out_cold_in_2:
    description: cold_in_2 target, K
    type: number
  T_out_hot_in_1:
    description: hot_in_1 target, K
    type: number
  T_out_hot_in_2:
    description: hot_in_2 target, K
    type: number
  cp_cold_in_1_W_per_K:
    description: analysis CP for cold_in_1, W/K (overrides the package-derived cp)
    type: number
  cp_cold_in_2_W_per_K:
    description: analysis CP for cold_in_2, W/K (overrides the package-derived cp)
    type: number
  cp_hot_in_1_W_per_K:
    description: analysis CP for hot_in_1, W/K (overrides the package-derived cp)
    type: number
  cp_hot_in_2_W_per_K:
    description: analysis CP for hot_in_2, W/K (overrides the package-derived cp)
    type: number
  dT_min:
    description: minimum approach, K (default 10)
    type: number
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V2086` | R0 | `info.QH_min_W` | 20000 | 20000 | rel 0.001 | pass |
| `V2086` | R0 | `info.QC_min_W` | 60000 | 60000 | rel 0.001 | pass |
| `V2086` | R0 | `info.pinch_T_hot_K` | 363.15 | 363.15 | abs 0.01 | pass |
| `V2086` | R0 | `info.pinch_T_cold_K` | 353.15 | 353.15 | abs 0.01 | pass |

- `V2086`: Kemp, User Guide on Process Integration for the Efficient Use of Energy (the Linnhoff four-stream problem table): hot 170->60 C CP 3.0 kW/K, hot 150->30 C CP 1.5, cold 20->135 C CP 2.0, cold 80->140 C CP 4.0; targets QHmin 20 kW, QCmin 60 kW at dTmin 10 K. The cp_*_W_per_K params pin the analysis CPs to the book's constant values, so the problem table is the book's arithmetic; the N2 feed flows (101.01 / 50.505 / 67.34 / 134.68 mol/s, cp_molar(N2) stand-ins) size only the outlet flashes.

## References

- docs/unit-catalogue-plan.md §2 U-C 10

> V2086 runs the Kemp four-stream problem-table basis; engineering deliverable (utility targets), not a balanced solver unit.
