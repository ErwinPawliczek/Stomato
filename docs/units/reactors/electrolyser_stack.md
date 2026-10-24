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
| `V1-ELECTROLYSER` | R0 | `info.thermoneutral_voltage_V` | 1.481 | 1.48953 | abs 0.0005 | assessed miss |

- `V1-ELECTROLYSER`: Züttel, Borgschulte & Schlapbach (eds.), Hydrogen as a Future Energy Carrier, Wiley-VCH 2008, ch. 1 §1.1, p. 5 (ISBN 978-3-527-30817-0): 'Electrolysis at ambient temperature and pressure requires a minimum voltage of 1.481 V and therefore, a minimum energy of 39.4 kWh kg−1 hydrogen' — a check on the formation data, not an echo of the model
  - assessed: The Faraday flows (n(H2) = η·I·N/(2F) ≈ 1.0157 mol/s, O2 half that) are closed-form on the inputs and live as a unit test in tests/units/reactors/test_reactors.py, not here. The one case oracle is the thermoneutral voltage against the printed source value: measured 1.48953 V from the actual stream balance (H_out − H_in)/(2F·n_H2) at the 298.15 K liquid-water feed — +0.576 % above the printed 1.481 V, a miss of 0.0085 V against the ±0.0005 V book-rounding tolerance. The direction and size match the databank's liquid-water formation enthalpy sitting ~1.6 kJ/mol more endothermic than the 285.83 kJ/mol HHV anchor the source value encodes; recorded as a databank finding, not tuned away.

## References

- docs/unit-catalogue-plan.md §2 U-F 9

> R0 implemented (U-F). Thermoneutral voltage is computed from the actual stream balance, (H_out − H_in)/(2F·n_H2) — on the 298.15 K liquid-water feed it measures 1.4895 V, +0.58 % against the printed 1.481 V (Züttel, Borgschulte & Schlapbach 2008, p. 5) — the databank miss is recorded, not tuned away, in the V1-ELECTROLYSER assessed note.
