# Sour water stripper (configuration) (`sour_water_strip_check`)

Family: **refining** · P&ID symbol: `SW`

Rigour ladder: R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `sour_water_in` | yes | sour water feed |
| outlet | `acid_gas_out` | yes | acid gas overhead |
| outlet | `clean_water_out` | yes | stripped water bottoms |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R2 | planned | — | a reboiled-stripper CONFIGURATION on the electrolyte package (T-09), not a bespoke unit — today via the `column` row's stripper configuration with a sour-water package (plan U-G 9; plan-to-registry mapping) |

## References

- docs/unit-catalogue-plan.md §2 U-H 12

> roadmap; kept as a palette reference row — resolve_level refuses until the sour-water package lands.
