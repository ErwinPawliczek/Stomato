# eos_cg — EOS-CG combustion-gas mixture model (placeholder)

family `helmholtz` · status **experimental** · adapter `ngdesign.thermo.helmholtz:UnavailablePackage`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert, acid_gas
- polar: True · electrolyte: False
- T window: 90–2000 K · P window: 1000–1e+08 Pa
- phases: V, L

## Parameters

- source: n/a
- provenance: n/a

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

Note: Placeholder row: the method is recorded, not implemented (teqp candidate, T-07).

### L4 cross-model pairs

- vs `aga8_dc92`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)
- vs `bwr_ls`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)
- vs `bwrs`: ok — n/a — refuses the slice feed: ComponentNotSupported: BWRSPackage has no parameters for component(s) ['C6+', 'H2O']; supported: ['C1', 'C2', 'C3', 'CO2', 'H2S', 'N2', 'iC4', 'iC5', 'nC4', 'nC5']
- vs `coolprop_heos`: ok — n/a — refuses the slice feed: ComponentNotSupported: CoolPropPackage has no parameters for component(s) ['C6+']; supported: ['C1', 'C2', 'C3', 'CO2', 'H2O', 'H2S', 'N2', 'iC4', 'iC5', 'nC4', 'nC5']
- vs `gerg2008`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)
- vs `mbwr`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)
- vs `nrtl`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)
- vs `pr`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)
- vs `pr78`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)
- vs `srk`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Gernert, J., Span, R., 'EOS-CG: A Helmholtz energy mixture model for humid combustion gases', Chem. Eng. Sci. 148, 59-74, 2016 (no implementation in this repo; the row is a catalogue placeholder and every property call raises UnavailableBackend)
