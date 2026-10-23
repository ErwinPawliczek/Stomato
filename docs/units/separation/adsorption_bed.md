# Adsorption bed (TSA/PSA) (`adsorption_bed`)

Family: **separation** · P&ID symbol: `X`

Rigour ladder: R0 planned, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed_in` | yes | gas to the bed |
| outlet | `product_out` | yes | treated product |
| outlet | `regen_out` | no | regeneration (tail-gas) outlet during the cycle |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | equilibrium capacity + breakthrough spec |
| R1 | planned | — | Langmuir isotherm, LUB |

## References

- docs/unit-catalogue-plan.md §2 U-D 9

> molecular-sieve dehydration (plan U-G 6) maps onto this row with a cycle — no separate treating row.
