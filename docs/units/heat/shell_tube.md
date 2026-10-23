# Shell-and-tube exchanger (`shell_tube`)

Family: **heat** · P&ID symbol: `E`

Rigour ladder: R0 provisional, R1 planned, R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | process feed |
| outlet | `outlet` | yes | exchanger outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.heat_exchange:HeatExchanger` | approach / duty with LMTD-F specification |
| R1 | planned | — | rating — U from ht film coefficients, TEMA type, F factor, ΔP both sides |
| R2 | planned | — | zoned (phase change), multi-pass with temperature cross |

Sizer plugin: `shell_tube`

### R0 parameters

```yaml
properties:
  T_out:
    description: outlet temperature spec, K
    type: number
  dP:
    description: pressure drop, Pa
    type: number
  duty_W:
    description: duty spec, W (one of T_out/duty_W)
    type: number
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-C 2

> the R0 row shares the HeatExchanger adapter; R1/R2 rating physics is the U-C family thread's work on the shared _physics/heat_transfer store.
