# Fired heater (`fired_heater`)

Family: **heat** · P&ID symbol: `FH`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | process feed (coil inlet) |
| outlet | `outlet` | yes | coil outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.heat.fired_heater:FiredHeater` | process duty from a T_out/duty_W spec; fuel demand from the mixture LHV with water as vapour |
| R1 | provisional | `ngdesign.units.heat.fired_heater_r1:FiredHeaterR1` | radiant/convective split (Lobo-Evans) with the fuel and flue-gas balance solved; bridgewall, stack and crossover temperatures reported |

### R0 parameters

```yaml
properties:
  T_out:
    description: outlet temperature spec, K (one of T_out/duty_W)
    type: number
  dP:
    description: coil pressure drop, Pa
    type: number
  duty_W:
    description: duty spec, W (one of T_out/duty_W)
    type: number
  efficiency:
    description: firing efficiency on the LHV basis, (0, 1]
    type: number
  fuel_composition:
    description: fuel component-id map; fuel flow is the solved demand
    type: object
type: object
```

### R1 parameters

```yaml
properties:
  T_out:
    description: outlet temperature spec, K (one of T_out/duty_W)
    type: number
  UA_convection_W_K:
    description: convection-section UA, W/K
    type: number
  air_T_K:
    description: combustion air temperature, K, default 298.15
    type: number
  air_composition:
    description: air mole fractions, default N2 0.79 / O2 0.21
    type: object
  alpha_Acp_m2:
    description: Lobo-Evans alpha*A_cp, m2
    type: number
  box_P_Pa:
    description: firebox pressure, Pa, default 101325
    type: number
  dP:
    description: coil pressure drop, Pa
    type: number
  duty_W:
    description: duty spec, W (one of T_out/duty_W)
    type: number
  excess_air_frac:
    description: excess air fraction over stoichiometric
    type: number
  exchange_factor:
    description: Lobo-Evans overall exchange factor, (0, 1]
    type: number
  fuel_composition:
    description: fuel component-id map; required at R1
    type: object
  h_conv_radiant_W_m2K:
    description: radiant-section convection, W/(m2 K), default 11.3565267
    type: number
  radiant_loss_frac:
    description: setting loss fraction of fired heat, default 0
    type: number
  tube_area_radiant_m2:
    description: radiant tube outside area, m2
    type: number
  tube_wall_excess_K:
    description: tube wall above mean radiant process T, K
    type: number
required:
- fuel_composition
- excess_air_frac
- alpha_Acp_m2
- exchange_factor
- tube_area_radiant_m2
- tube_wall_excess_K
- UA_convection_W_K
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V2083` | R0 | `info.fuel_LHV_J_per_mol` | 802125 | 802584 | rel 0.001 | pass |
| `V2105` | R1 | `info.T_bridgewall_K` | 1199.26 | 1199.48 | rel 0.02 | pass |
| `V2105` | R1 | `info.efficiency_LHV` | 0.75 | 0.74036 | rel 0.03 | pass |
| `V2105` | R1 | `info.Q_radiant_W` | 1.08562e+07 | 1.07757e+07 | rel 0.03 | pass |
| `V2105` | R1 | `info.radiant_flux_W_m2` | 38738.4 | 38356 | rel 0.03 | pass |

- `V2083`: NBSIR 82-2401, Heating Values of Natural Gas and Its Components (Table 14: methane net heat of combustion 802.125 kJ/mol at 288.15 K and 101.325 kPa). The package's formation-enthalpy LHV (water as VAPOUR, gas-phase standard states at 298.15 K) is 802.584 kJ/mol, +0.057% on the printed value - a reference-state difference, not a calculation choice.
- `V2105`: Kern, Process Heat Transfer, Example 19.1, "Calculation of a Furnace by the Method of Lobo and Evans" (transcribed from the Internet Archive full-text scan of the 1950 edition): a furnace designed for a total duty of 50,000,000 Btu/hr at 75 per cent overall efficiency (lower heating value basis); oil fuel of LHV 17,130 Btu/lb fired with 25 per cent excess air (17.44 lb air/lb fuel), air preheated to 400 F; wall loss 2 per cent of the fired heat; 60 tubes of 5 in. OD on 8.5 in. centres with 38 ft 6 in. exposed length give A_t = 3024 ft2 and alpha*A_cp = 1500 ft2; the recomputed overall exchange factor is 0.635 and the average tube temperature 800 F. The converged balance is struck "at about 1700 F", with radiant duty 37,050,000 Btu/hr and circumferential flux 12,280 Btu/(hr)(ft2).
  - assessed: Measured on the package: T_bridgewall 1199.5 K (printed "about 1700 F" = 1199.26 K, +0.02 per cent), efficiency_LHV 0.7404 (printed 0.75, -1.3), Q_radiant 10.78 MW (printed 37,050,000 Btu/hr = 10.856 MW, -0.7), flux 38,356 W/m2 (printed 12,280 Btu/(hr ft2) = 38,738 W/m2, -1.0). Carriers, not cited values: the fuel composition (Kern prints only the oil LHV, 17,130 Btu/lb = 39.85 kJ/g; the carrier nC10/C1 mix matches H/C = 2.302 implied by the printed flue analysis pCO2 0.1084 / pH2O 0.1248, but its LHV is 44.9 kJ/g, so the fuel mass flow is not anchored), the process coil stream (Example 19.1 is a design problem and names no coil fluid; the C1 carrier 600 -> 700 K at 5 bar realizes the printed duty and the 800 F average tube temperature through tube_wall_excess_K), and UA_convection (10,000 W/K; Example 19.1 sizes only the radiant section, and the convection rating first appears in Example 19.2). Residual gaps are chart flue enthalpies vs the PR package (Kern's flue gas at 476 Btu/lb for 1730 F) and the 60 F chart reference vs the 298.15 K formation basis, both inside the tolerances above.

## References

- docs/unit-catalogue-plan.md §2 U-C 7

> V2083 checks the methane LHV against NBSIR 82-2401 (802.125 kJ/mol at 288.15 K; package 802.584 kJ/mol on the 298.15 K formation basis, +0.057%). R1 is anchored on Kern Example 19.1 (V2105) — the solved radiant section closes within 1.5% of the printed 1700 F bridgewall, 0.75 efficiency, 37,050,000 Btu/hr radiant duty and 12,280 Btu/(hr ft2) flux; fuel composition, coil fluid and convection UA are documented carriers.
