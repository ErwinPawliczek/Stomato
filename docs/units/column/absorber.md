# Absorber (feed-determined) (`absorber`)

Family: **column** · P&ID symbol: `T`

Rigour ladder: R0 provisional, R2 provisional, R3 planned

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
| R3 | planned | — | rate-based stages |

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

> the amine-specific rows live in the treating family; this row is the generic solvent absorber. R2 V1 gap — provisional without a case (searched data/validation/ and data/validation_units/column/ for absorber cases; the only absorber V1 case on main is R0's V1-kremser-absorber-seader53, whose printed fractions-not-absorbed are anchored to Example 5.3's 97.5 F chart-estimated K-values carried as Kremser k_overrides — a different thermodynamic basis from the package K-values R2 runs on — so the case is not transferable without re-deriving anchors, which the V1 conventions forbid). R2 is covered by closed-form identity and equilibrium-pair tests.
