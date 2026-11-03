# Atmospheric crude column (`crude_column`)

Family: **refining** · P&ID symbol: `T`

Rigour ladder: R0 provisional, R2 planned

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
| R2 | planned | — | MESH with side strippers, pumparounds, stripping steam, overflash; the column's relaxation start (initialization relaxation, over the whole stage graph) now converges a crude-shaped graph - 10 stages nC5/nC8/nC11/nC14 at 1.5 bar, partial condenser, no reboiler, bottom steam, one 3-stage steam stripper (11 s; the standard start lands on a free-water branch, 42 s). Blocker re-measured on the R0 crude cut into 16 pseudos (22 species, 12 stages, kero/diesel/AGO strippers at the R0 cut-point rates, 631.75 K, 2 bar) - after Newton from the relaxed main column stalls, the inside-out fallback dies inside the PR package's PT flash (UnconvergedError, End of SS without convergence, 37 s); and the slate's heavy-end second liquid (see preflash R2) needs pooled stage liquids, which the relaxation start does not carry |

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

## References

- docs/unit-catalogue-plan.md §2 U-H 3

> V1 gap — provisional without a case. The open Bagajewicz & Ji (2001) copy prints no per-cut product-yield table (transcription gaps recorded in data/validation_units/refining/s0_reference.yaml), so the former V2103 pin (a closed-form recomputation of the adapter's own cut arithmetic) was moved to a closed-form test in tests/units/refining/test_separation.py. Column extensions still planned (P1-11).
