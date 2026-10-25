# Reboiled stripper (`reboiled_stripper`)

Family: **column** · P&ID symbol: `T`

Rigour ladder: R0 provisional, R2 provisional, R3 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed` | yes | liquid feed to the top stage |
| outlet | `overhead` | yes | stripped overhead |
| outlet | `bottoms` | yes | lean bottoms |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.column_shortcut.stripper:ReboiledStripper` | Kremser on the stripping side |
| R2 | provisional | `ngdesign.units.column_shortcut.reboiled_stripper_r2:ReboiledStripperR2` | one-tear MESH (kettle only) via the column API; specs met to the column's _SPEC_TOL — the loose column-core spec gate (tracked as issue 248; rate-spec convergence there is a core defect; reboiler_duty_W refused — the kettle-only core hits a singular Newton system for it). The nC4/nC5 bench feed is withdrawn per the PR 292 ruling — the kettle-only column core does not converge on it (tracked as issue 248). The component_recovery 0.9 NC4 case on the C1/NC4 anchor feed is infeasible on this core (residual stuck ~7.5e-3, above the spec gate) and is pinned xfail(strict=True) in the test file. |
| R3 | planned | — | rate-based stages |

### R0 parameters

```yaml
properties:
  N:
    description: ideal stages, positive
    type: number
  k_overrides:
    description: '{cid: K} replacing thermo k_values per component'
    type: object
  vapour_flow:
    description: stripping vapour flow, mol/s
    type: number
required:
- N
type: object
```

### R2 parameters

```yaml
additionalProperties: false
properties:
  n_stages:
    description: stages including the kettle reboiler (stage N); feed on stage 1
    minimum: 2
    type: integer
  pressure_profile:
    description: stage pressures, Pa abs (scalar = uniform; list = per stage, top
      to bottom); default feed.P
    oneOf:
    - exclusiveMinimum: 0
      type: number
    - items:
        exclusiveMinimum: 0
        type: number
      type: array
  spec:
    description: exactly one of boilup_ratio, bottoms_rate (mol/s), distillate_rate
      (mol/s), component_recovery ({component, value, product})
    maxProperties: 1
    minProperties: 1
    type: object
required:
- n_stages
- spec
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-kremser-stripper-seader98` | R0 | `info.bottoms_SO2` | 0.0063 | 0.00629998 | abs 0.0001 | pass |
| `V1-kremser-stripper-seader98` | R0 | `info.overhead_1,3-butadiene` | 0.99186 | 0.991815 | abs 0.001 | pass |
| `V1-kremser-stripper-seader98` | R0 | `info.bottoms_1,2-butadiene` | 0.01134 | 0.0113541 | abs 0.0003 | pass |
| `V1-kremser-stripper-seader98` | R0 | `info.bottoms_n-decane` | 12.441 | 12.4394 | abs 0.002 | pass |

- `V1-kremser-stripper-seader98`: Seader, Henley & Roper, 3rd ed., Example 9.8, p. 372: SO2/butadienes stripped by nitrogen from butadiene-sulfone liquor, converged N = 3 row (V0 = 94.3 lbmol/h): fS = 0.0050 (SO2), 0.016 (B3), 0.045 (B2), 0.9874 (BS). Butadiene sulfone is not in the component registry; the example carries the documented n-decane stand-in with the book's K-values as k_overrides.

## References

- docs/unit-catalogue-plan.md §2 U-E 4

> sour-water stripping (plan U-G 9) is a reboiled-stripper configuration on an electrolyte package (T-09) — no separate treating row. R2 V1 gap — provisional without a case (searched Seader, Henley & Roper 3rd ed. rigorous-methods chapter and Kister, Distillation Design (1992) stripper examples; no printed rigorous reboiled-stripper example with its inputs and printed product flows or duties was found, so a V1 case cannot be transcribed without reconstruction; R2 is covered by closed-form identity and equilibrium-pair tests against the column row and thermo bubble/dew points).
