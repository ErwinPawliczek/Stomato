# Absorber (feed-determined) (`absorber`)

Family: **column** · P&ID symbol: `T`

Rigour ladder: R0 provisional, R2 provisional, R3 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `gas_in` | yes | feed gas |
| inlet | `solvent_in` | yes | lean solvent |
| outlet | `gas_out` | yes | treated gas |
| outlet | `rich_out` | yes | rich solvent |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.column_shortcut.absorber:Absorber` | Kremser stage count (the kremser correlation plugin exists in sizing); two-feed split lets lean-solvent components strip |
| R2 | provisional | `ngdesign.units.column_shortcut.absorber_r2:AbsorberR2` | zero-tear MESH via the column API (inside-out + NS fallback); duty_W = boundary energy residual |
| R3 | provisional | `ngdesign.units.column.rate_based_units:AbsorberR3` | rate-based (Krishna-Taylor) packed segments - separate vapour/liquid balances, interface equilibrium from the package fugacity coefficients, effective-diffusivity film fluxes with Onda (1968) random-packing kG, kL and wetted area, Chapman-Enskog and Wilke-Chang diffusivities, Chilton-Colburn/penetration heat transfer; reduces to R2 as transfer_factor grows (measured 5.6e-7 max outlet deviation at 1e4); duty_W = boundary energy residual. Random packing only - sieve-tray (AIChE 1958, Chan-Fair 1984) coefficients were not adopted because their constants could not be confirmed from a fetched source |

### R0 parameters

```yaml
properties:
  N:
    description: ideal stages, positive
    type: number
  k_overrides:
    description: '{cid: K} replacing thermo k_values per component (book-estimated-K
      reference cases)'
    type: object
required:
- N
type: object
```

### R2 parameters

```yaml
additionalProperties: false
properties:
  n_stages:
    description: equilibrium stages (top = 1)
    minimum: 2
    type: integer
  pressure_profile:
    description: stage pressures, Pa abs (scalar = uniform; list = per stage, top
      to bottom); default gas_in.P
    oneOf:
    - exclusiveMinimum: 0
      type: number
    - items:
        exclusiveMinimum: 0
        type: number
      type: array
required:
- n_stages
type: object
```

### R3 parameters

```yaml
additionalProperties: false
properties:
  column_diameter_m:
    description: packed-bed diameter
    exclusiveMinimum: 0
    m: null
    type: number
  critical_surface_tension_N_m:
    description: critical surface tension of the packing material sigma_c, N/m
    exclusiveMinimum: 0
    type: number
  n_stages:
    description: packed segments (rate-based stages), top = 1
    minimum: 1
    type: integer
  nominal_size_m:
    description: nominal packing size D_p, m (Onda kG constant 5.23 at >= 15 mm, 2.00
      below)
    exclusiveMinimum: 0
    type: number
  packed_height_m:
    description: total packed height, m (split equally over the segments)
    exclusiveMinimum: 0
    type: number
  pressure_profile:
    description: stage pressures, Pa abs (scalar = uniform; list = per stage, top
      to bottom)
    oneOf:
    - exclusiveMinimum: 0
      type: number
    - items:
        exclusiveMinimum: 0
        type: number
      type: array
  specific_area_m2_m3:
    description: total packing area a_t, m2/m3
    exclusiveMinimum: 0
    type: number
  surface_tension_N_m:
    description: liquid surface tension, N/m (the thermo contract carries none)
    exclusiveMinimum: 0
    type: number
  transfer_factor:
    description: multiplier on every film conductance and heat-transfer coefficient
      (default 1); large values reduce each segment to an equilibrium stage
    exclusiveMinimum: 0
    type: number
required:
- n_stages
- column_diameter_m
- packed_height_m
- nominal_size_m
- specific_area_m2_m3
- critical_surface_tension_N_m
- surface_tension_N_m
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-kremser-absorber-seader53` | R0 | `info.f_not_absorbed_C1` | 0.969 | 0.968985 | abs 0.0005 | pass |
| `V1-kremser-absorber-seader53` | R0 | `info.f_not_absorbed_C2` | 0.874 | 0.874238 | abs 0.0005 | pass |
| `V1-kremser-absorber-seader53` | R0 | `info.f_not_absorbed_C3` | 0.647 | 0.647276 | abs 0.0005 | pass |
| `V1-kremser-absorber-seader53` | R0 | `info.f_not_absorbed_nC4` | 0.119 | 0.119976 | abs 0.001 | pass |
| `V1-kremser-absorber-seader53` | R0 | `info.f_not_absorbed_nC5` | 0.00112 | 0.0011174 | abs 5e-06 | pass |
| `V1-kremser-absorber-seader53` | R0 | `info.f_not_stripped_nC4` | 0.168 | 0.167977 | abs 0.0005 | pass |
| `V1-kremser-absorber-seader53` | R0 | `info.f_not_stripped_nC5` | 0.654 | 0.654689 | abs 0.001 | pass |
| `V1-kremser-absorber-seader53` | R0 | `info.f_not_stripped_C6+` | 0.9995 | 0.999515 | abs 0.0005 | pass |

- `V1-kremser-absorber-seader53`: Seader, Henley & Roper, 3rd ed., Example 5.3, p. 188: hydrocarbon-rich gas absorbed by oil, N = 6, 800 lbmol/h gas at 105 F / 400 psia, 165 lbmol/h absorbent oil at 90 F; printed fA/fS table at K-values estimated at 97.5 F (carried by the example_case as k_overrides).

## References

- docs/unit-catalogue-plan.md §2 U-E 3
- Taylor, Kooijman & Hung 1994, Comput. Chem. Eng. 18, 205-217
- Onda, Takeuchi & Okumoto 1968, J. Chem. Eng. Japan 1, 56-62

> the amine-specific rows live in the treating family; this row is the generic solvent absorber. R2 V1 gap — provisional without a case (searched data/validation/ and data/validation_units/column/ for absorber cases; the only absorber V1 case on main is R0's V1-kremser-absorber-seader53, whose printed fractions-not-absorbed are anchored to Example 5.3's 97.5 F chart-estimated K-values carried as Kremser k_overrides — a different thermodynamic basis from the package K-values R2 runs on — so the case is not transferable without re-deriving anchors, which the V1 conventions forbid). R2 is covered by closed-form identity and equilibrium-pair tests.
