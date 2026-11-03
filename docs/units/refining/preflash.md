# Preflash / flash column (`preflash`)

Family: **refining** · P&ID symbol: `FL`

Rigour ladder: R0 provisional, R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed_in` | yes | heated assay feed |
| outlet | `vapor_out` | yes | flashed vapor |
| outlet | `liquid_out` | yes | flashed liquid |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.refining.preflash:Preflash` | flash drum on the assay stream (spec U-H1 PT flash at the drum conditions; vapour to vapor_out, pooled liquid to liquid_out) |
| R2 | planned | — | short MESH; re-measured on the P1-13 tree - a PT flash of the 48-species example feed costs ~2 s on the PR package (Michelsen stability tests dominate), so one flash-surface sweep of a 5-stage partial-condenser column (D = 150 mol/s) takes ~260 s; on the fugacity surface the sweeps take ~0.1 s but diverge (M ~ 1.5, H ~ 1.3) and Naphtali-Sandholm stalls at M = 1.0 after 25 passes |

### R0 parameters

```yaml
properties:
  P:
    description: drum pressure (Pa abs, default the inlet pressure)
    type: number
  T:
    description: drum temperature (K)
    type: number
required:
- T
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-H 6

> V1 gap — provisional without a case. The drum conditions are published (Gary et al., Petroleum Refining, p. 66), but no open source prints a flashed-vapour yield for that basis, so the former V2105 pin (a regression value computed by the registered PR package) was withdrawn; plumbing and vapour-fraction consistency live as closed-form tests in tests/units/refining/test_separation.py.
