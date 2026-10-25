# Electrolyser / fuel cell stack (`electrolyser_stack`)

Family: **reactors** · P&ID symbol: `FC`

Rigour ladder: R0 provisional, R1 provisional

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
| R1 | provisional | `ngdesign.units.reactors.electrolyser_r1:ElectrolyserStackR1` | Ulleberg (2003) eq. 4 cell voltage on the reversible voltage from ln_keq on H2O(g) -> H2 + 1/2 O2, the liquid-water p_sat correction (Poynting neglected) and the optional Nernst term, with the eq. 9 form Faradaic efficiency; delegation to R0 by composition. V1 gap, recorded with PR 305 — Ulleberg 2003 prints the polarisation curves mostly as figures and no printed (current, voltage, temperature) point with the stack area was found in the searched sources (Ulleberg 2003 Tables 1-2 and text; Ursua, Gandia & Sanchis, Proc. IEEE 100 (2012) 410-426; the LeRoy/Bowen/LeRoy 1980 alkaline data), so the polarisation closed form is covered by unit tests on printed test coefficients. The ulleberg2003 preset is added only when Table 1 is transcribed with page and equation numbers. |

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

### R1 parameters

```yaml
properties:
  T_K:
    "K \u2014 must equal the inlet T (no silent re-heating)": null
    description: operating temperature
    type: number
  area_m2:
    description: electrode area per cell
    m2: null
    type: number
  current_A:
    A: null
    description: stack current
    type: number
  faradaic:
    description: 'optional {f1: A2/m4, f2}: Ulleberg eq. 9 form eta_F = f2*i^2/(f1
      + i^2); default 1'
  n_cells:
    description: cells in series
    type: number
  polarisation:
    description: 'Ulleberg (2003, Int. J. Hydrogen Energy 28:21-33) eq. 4 coefficients
      {r1: Ohm m2, r2: Ohm m2/degC, s: V, t1: m2/A, t2: m2 degC/A, t3: m2 degC2/A};
      i in A/m2, T in degC, log10. The named preset ''ulleberg2003'' is refused until
      Table 1 is transcribed with page and equation numbers'
  pressure_correction:
    description: true adds the Nernst term (R*T/2F)*ln[(P/P0)^1.5] with P0 = 1e5 Pa;
      default false
    type: boolean
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
