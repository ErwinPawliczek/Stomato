# Electrolyser / fuel cell stack (`electrolyser_stack`)

Family: **reactors** · P&ID symbol: `FC`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed (no H2 or O2 present) |
| outlet | `h2_out` | yes | pure hydrogen product |
| outlet | `o2_out` | yes | coproduct oxygen plus everything else fed |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.reactors.electrolyser:ElectrolyserStack` | Faraday's law n(H2) = η·I·N/(2F); power = V·I·N is electrical work |
| R1 | planned | — | polarisation curve |

### R0 parameters

```yaml
properties:
  cell_voltage_V:
    V: null
    description: cell voltage
    type: number
  current_A:
    A: null
    description: stack current
    type: number
  faradaic_efficiency:
    description: charge efficiency in (0, 1]; default 1
    type: number
  n_cells:
    description: cells in series
    type: number
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-ELECTROLYSER` | R0 | `power_W` | 350000 | 350000 | rel 1e-06 | pass |
| `V1-ELECTROLYSER` | R0 | `info.cell_voltage_V` | 1.75 | 1.75 | abs 1e-06 | pass |
| `V1-ELECTROLYSER` | R0 | `info.thermoneutral_voltage_V` | 1.25315 | 1.25315 | abs 0.0001 | pass |
| `V1-ELECTROLYSER` | R0 | `outlet.h2_out.molar_flow` | 1.0157 | 1.0157 | abs 0.0001 | pass |
| `V1-ELECTROLYSER` | R0 | `outlet.o2_out.composition.O2` | 0.010261 | 0.0102612 | abs 0.0001 | pass |

- `V1-ELECTROLYSER`: Closed form, Faraday's law: n(H2) = η·I·N/(2F) = 0.98·2000·100/(2·96485) ≈ 1.0157 mol/s; power = V·I·N = 350 kW

## References

- docs/unit-catalogue-plan.md §2 U-F 9

> R0 implemented (U-F). Thermoneutral voltage reported on the databank's water-vapour basis (≈ 1.253 V); liquid-water HHV (1.481 V) deliberately not used.
