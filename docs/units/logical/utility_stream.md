# Utility stream source/sink (`utility_stream`)

Family: **logical** · P&ID symbol: `UTL`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | no | process stream to absorb the utility (sink side) |
| outlet | `outlet` | yes | utility stream at the declared level |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.logical.utility_stream:UtilityStream` | metering pass-through reporting utility_cost_rate = price x mass_flow (currency per kg basis). electricity refused at R0 (no stream basis; per-J form on a declared power param is a later round). closed-form only; definitional unit (no open textbook worked example; pricing data out of scope per spec) |

### R0 parameters

```yaml
properties:
  kind:
    enum:
    - steam_lp
    - steam_mp
    - steam_hp
    - cooling_water
    - fuel_gas
    - electricity
    - refrigerant
    type: string
  price:
    description: currency per kg of the stream (fluid utilities); reported as info.utility_cost_rate
      = price x mass_flow in currency/s (pass-through, not physics)
    type: number
required:
- kind
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-A 9

> roadmap R0.
