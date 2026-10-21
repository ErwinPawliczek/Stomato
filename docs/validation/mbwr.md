# mbwr — Modified BWR (Starling 1976, 27-compound set) (placeholder)

family `helmholtz` · status **experimental** · adapter `ngdesign.thermo.helmholtz:UnavailablePackage`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert, acid_gas, water
- polar: True · electrolyte: False
- T window: 90–680 K · P window: 1000–1e+08 Pa
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
- vs `bwr_ls`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)
- vs `bwrs`: ok — n/a — refuses the slice feed: ComponentNotSupported: BWRSPackage has no parameters for component(s) ['C6+', 'H2O']; supported: ['C1', 'C2', 'C3', 'CO2', 'H2S', 'N2', 'iC4', 'iC5', 'nC4', 'nC5']
- vs `coolprop_heos`: ok — n/a — refuses the slice feed: ComponentNotSupported: CoolPropPackage has no parameters for component(s) ['C6+']; supported: ['C1', 'C2', 'C3', 'CO2', 'H2O', 'H2S', 'N2', 'iC4', 'iC5', 'nC4', 'nC5']
- vs `eos_cg`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)
- vs `gerg2008`: ok — n/a — refuses the slice feed: ComponentNotSupported: GERGPackage has no parameters for component(s) ['C6+', 'H2O']; supported: ['C1', 'C2', 'C3', 'CO2', 'H2S', 'N2', 'iC4', 'iC5', 'nC4', 'nC5']
- vs `nrtl`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)
- vs `pr`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)
- vs `pr78`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)
- vs `srk`: ok — n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Starling, K. E., Cox, K. W., Kwok, Y. C., et al., 'Modified BWR Equation of State Parameters for Twenty-Seven Compounds', ORO-5249-2 (U.S. ERDA report), Appendix B, 1976 (no implementation in this repo; the row is a catalogue placeholder and every property call raises UnavailableBackend)
