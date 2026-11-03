# Atmospheric crude column (`crude_column`)

Family: **refining** · P&ID symbol: `T`

Rigour ladder: R0 provisional, R2 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `crude_in` | yes | heated crude feed |
| inlet | `stripping_steam` | no | stripping steam; its water (H2O) reports to the overhead |
| outlet | `overhead` | yes | naphtha overhead |
| outlet | `kero_out` | yes | kerosene side draw |
| outlet | `diesel_out` | yes | diesel side draw |
| outlet | `ago_out` | yes | atmospheric gas oil side draw |
| outlet | `bottoms` | yes | reduced crude bottoms |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.refining.crude_column:CrudeColumn` | cut-point fractionation (TBP cut points, gap/overlap spec) — spec U-H1 sharp cut, light ends and water to the overhead; optional stripping_steam inlet carries its water to the overhead at R0 (one net duty) |
| R2 | provisional | `ngdesign.units.refining.crude_column_r2:CrudeColumnR2` | MESH over the stage graph (main column plus three steam side strippers as one Newton system), partial condenser, no reboiler, stripping steam under the bottom stage and into each stripper, overflash reported. Pooled stage liquids - the slate's heaviest pseudos split off a second liquid on the flash-zone and bottom stages - read the pooled liquid's own liquid-liquid split (no flash per stage K); relaxation cold start. Example (16-cut slate, 12 stages, 3-stage strippers) converges in ~45 s with a 1 mW closure residual. No pumparounds at this level |

### R0 parameters

```yaml
properties:
  cut_points_K:
    description: four ascending TBP cut boundaries (K) for the five products
    items:
      type: number
    type: array
  draws:
    description: per-port {T, P} draw conditions (default the feed state)
    type: object
  overlap_K:
    description: linear split band (K) at each cut boundary (default 0)
    type: number
required:
- cut_points_K
type: object
```

### R2 parameters

```yaml
additionalProperties: false
properties:
  distillate_rate_mol_s:
    description: overhead vapour rate, mol/s (the condenser's degree of freedom)
    exclusiveMinimum: 0
    type: number
  feed_stage:
    description: flash-zone stage the crude enters; the stripping steam not taken
      by the strippers enters under stage n_stages
    minimum: 3
    type: integer
  n_stages:
    description: main-column equilibrium stages, stage 1 the partial condenser
    minimum: 4
    type: integer
  pressure_profile:
    description: stage pressures, Pa abs (scalar or per-stage list); default crude_in.P
  strippers:
    description: per side port (kero_out, diesel_out, ago_out) a steam side stripper
      {draw_stage, return_stage, n_stages, steam_mol_s, product_rate_mol_s}; its product
      rate fixes it, the draw is its outcome
    type: object
required:
- n_stages
- feed_stage
- distillate_rate_mol_s
- strippers
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-H 3

> V1 gap — provisional without a case. The open Bagajewicz & Ji (2001) copy prints no per-cut product-yield table (transcription gaps recorded in data/validation_units/refining/s0_reference.yaml), so the former V2103 pin (a closed-form recomputation of the adapter's own cut arithmetic) was moved to a closed-form test in tests/units/refining/test_separation.py. Column extensions still planned (P1-11).
