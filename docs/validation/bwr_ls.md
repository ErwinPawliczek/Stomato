# bwr_ls — BWR-Lee-Starling (placeholder)

family `helmholtz` · status **experimental** · adapter `ngdesign.thermo.helmholtz:UnavailablePackage`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert, acid_gas
- polar: True · electrolyte: False
- T window: 95–600 K · P window: 1000–7e+07 Pa
- phases: V, L

## Parameters

- source: n/a
- provenance: n/a

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

Note: Placeholder row: the method is recorded, not implemented.

### L4 cross-model pairs

- vs `aga8_dc92`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)
- vs `bwrs`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)
- vs `coolprop_heos`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)
- vs `eos_cg`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)
- vs `gerg2008`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)
- vs `mbwr`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)
- vs `nrtl`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)
- vs `pr`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)
- vs `pr78`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)
- vs `srk`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Lee, B. I., Starling, K. E., Starling's BWR equation variant as summarized in 'Thermodynamic Property Prediction of Light Hydrocarbons and Related Fluids' (no implementation in this repo; the row is a catalogue placeholder and every property call raises UnavailableBackend)
