# Claus sulfur recovery (`sulfur_recovery`)

Family: **treating** · P&ID symbol: `SRU`

Rigour ladder: R0 provisional, R2 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `acid_gas_in` | yes | acid gas feed |
| outlet | `tail_gas_out` | yes | tail gas |
| outlet | `sulfur_out` | yes | liquid sulfur |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.treating.sulfur_recovery:SulfurRecovery` | condenses S8 only (databank species with usable formula + formation data — recorded choice); hydrocarbons pass through unburned at R0; V1 case on GPSA EDB Sect. 22 Ex. 22-1 printed stage results — the example's printed overall recovery is not accessible in any copy reachable (official GPSA workbook companion ends at the first converter), so it is a documented V1 gap and the level stays provisional |
| R2 | provisional | `ngdesign.units.treating.sulfur_recovery_r2:SulfurRecoveryR2` | Gibbs equilibrium per catalytic converter (isothermal; S6/S8 ± COS/CS2); furnace = R0 rule (S2 data missing); complete sulfur condensation (package S8 Psat unusable); V1 gap — no printed R2-level case found. The row's only printed Claus example (GPSA EDB Sect. 22 Ex. 22-1) is a plant material balance recorded at R0, and no reachable printed source transcribes per-stage converter equilibrium compositions with approach temperatures, so the level stays provisional |

### R0 parameters

```yaml
properties:
  P:
    Pa abs: null
    description: process pressure
    type: number
  T_condenser:
    K: null
    description: sulfur condenser temperature
    type: number
  T_thermal:
    K: null
    description: thermal-stage (reaction-furnace) temperature
    type: number
  catalytic_stages:
    description: one entry per catalytic stage
    each with T (K) and exactly one of conversion (fraction) or approach_K (K): null
    type: array
  reaction_set:
    U-01b pattern (a)): null
    description: flowsheet-owned reaction set (H2S burn + Claus reaction
    type: object
  thermal_conversion:
    description: fraction of the post-burn H2S consumed by the Claus reaction in the
      thermal stage
    type: number
type: object
```

### R2 parameters

```yaml
properties:
  P:
    description: process pressure, Pa abs
    type: number
  T_condenser:
    description: sulfur condenser temperature, K
    type: number
  T_thermal:
    description: thermal-stage (reaction-furnace) temperature, K
    type: number
  catalytic_stages:
    description: one entry per catalytic Gibbs equilibrium stage, each with T (K)
      and optional approach_K (K); conversion stages are refused
    type: array
  extra_species:
    description: additional converter species from the supported set (CO, COS, CS2,
      H2)
    type: array
  reaction_set:
    description: flowsheet-owned reaction set (H2S burn + Claus reaction, U-01b pattern
      (a))
    type: object
  thermal_conversion:
    description: fraction of the post-burn H2S consumed by the Claus reaction in the
      thermal stage (the R0 furnace rule)
    type: number
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1202-sulfur-recovery-gpsa` | R0 | `info.stage_0_extent_mol_s` | 0.0052802 | 0.00501688 | abs 1e-06 | assessed miss |

- `V1202-sulfur-recovery-gpsa`: GPSA Engineering Data Book, Sect. 22, Example 22-1 "Claus Process Calculation" (printed inputs on a 100 LT/D sulfur basis: acid gas 60.65 mol% H2S, 32.17 CO2, 6.20 H2O, 0.98 hydrocarbons as C1 at 110 F, 20.7 psia; stoichiometric air for the one-third H2S burn plus full HC burn at 180 F with 0.0297 humidity; furnace outlet 19.1 psia; first condenser 350 F; first converter at equilibrium). Printed thermal-stage Claus extent x = 135.16 lb-mol/hr of the 194.05 lb-mol/hr H2S surviving the burn (Fig. 22-27 heat-balance intercept; the official GPSA Section22.xlsx workbook companion intercepts x = 135.555 at 2163.3 F). Printed first-converter Claus extent x = 38.0177 lb-mol/hr H2S (workbook Step 5 intercept; converter outlet 581 F read from Fig. 22-27, 582.7 F by the workbook Kp polynomial). GPSA flows are lb-mol/hr; the case runs the printed lb-mol/hr numbers as mol/hr, i.e. at 1/453.59 scale (the equilibrium extent fraction is scale-free and the expected value uses the same scaling).
  - assessed: DOCUMENTED GAP - the example's printed overall recovery is not checked: no copy reachable to this repo reproduces the example's final recovery step. The official GPSA Section22.xlsx workbook companion ends at the first catalytic converter plus an incinerator sheet, and the Kohl & Nielsen, Gas Purification, 5th ed., ch. 8 copies found online expose only front matter. Searched: GPSA posted workbook (gspsa.org), pdfcoffee and Scribd Section 22 reproductions (previews truncate before pp. 22-20+), vdoc.pub Kohl & Nielsen. The case instead checks the PRINTED first-converter extent: 38.0177 lb-mol/hr H2S consumed at equilibrium, on the S8 basis the workbook itself states is within 1% of total overall conversion. Inputs derived from printed values only (never back-solved): thermal_conversion = 135.16/194.05; unit extent = H2S (lb-mol/hr run as mol/hr) / 2 / 3600 (the unit's extent is per mol SO2 consumed). Known adapter difference, documented not hidden: the R0 unit does not combust the 0.98 mol% hydrocarbons, so the 9.4 lb-mol/hr of O2 meant for HC burn passes through unreacted and the tail gas carries CH4 + O2 where the book carries CO2 + H2O (~0.8% effect on total moles). Measured stage_0_extent_mol_s 0.0050169 (36.1 H2S consumed on the same scale) vs the printed 38.0177: -5.0%, a recorded miss at the printed rounding (the JANAF-based equilibrium behind ngdesign.units._physics.kinetics.ln_keq and ngdesign.data.formation sits ~5% below the GPSA Fig. 22-27 chart read at the converter outlet temperature). Measured sulfur_recovery_fraction 0.8827 — no printed value exists to check it against (the example's final recovery step is not accessible); recorded for transparency, on the R0 basis of one thermal stage + one catalytic converter and no HC combustion.

## References

- docs/unit-catalogue-plan.md §2 U-G 5

> roadmap; S2 slice (plan §2b). Sour-water stripping is NOT a row here — it is a reboiled-stripper configuration on the electrolyte package (T-09, plan U-G 9). R2 V1 gap recorded in the R2 level note — searched GPSA Sect. 22 and the row's printed examples; Ex. 22-1 is the only Claus case and it is R0-level.
