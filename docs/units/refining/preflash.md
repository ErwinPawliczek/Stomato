# Preflash / flash column (`preflash`)

Family: **refining** · P&ID symbol: `FL`

Rigour ladder: R0 provisional, R2 provisional

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
| R2 | provisional | `ngdesign.units.refining.preflash_r2:PreflashR2` | one-tear MESH rectifier (partial condenser, no reboiler, feed on the bottom stage), stage liquid pooled (pool_liquids - the PR package splits a heavy-end second liquid off the crude slate, 3 % on the bottom stage). Converges since the condenser band reaches below the feed (top stage ~150 K under it). The example cuts the R0 crude into 16 pseudos (22 species, ~13 s); on the 48-species default slate each saturated product's PT flash alone spends ~45 s in Michelsen stability tests |

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

### R2 parameters

```yaml
additionalProperties: false
properties:
  distillate_rate_mol_s:
    description: condenser vapour product (vapor_out), mol/s
    exclusiveMinimum: 0
    type: number
  n_stages:
    description: equilibrium stages, partial condenser on 1, feed on N
    minimum: 2
    type: integer
  pressure_profile:
    description: stage pressures, Pa abs (scalar or per-stage list); default feed_in.P
required:
- n_stages
- distillate_rate_mol_s
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-H 6

> V1 gap — provisional without a case. The drum conditions are published (Gary et al., Petroleum Refining, p. 66), but no open source prints a flashed-vapour yield for that basis, so the former V2105 pin (a regression value computed by the registered PR package) was withdrawn; plumbing and vapour-fraction consistency live as closed-form tests in tests/units/refining/test_separation.py.
