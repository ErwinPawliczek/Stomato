# coolprop_heos — CoolProp pure Helmholtz (HEOS) fluids and mixtures

family `helmholtz` · status **validated** · adapter `ngdesign.thermo.helmholtz:CoolPropPackage`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert, water, acid_gas
- polar: True · electrolyte: False
- T window: 90–680 K · P window: 1000–1e+08 Pa
- phases: V, L, VLL, VLLE

## Parameters

- source: n/a
- provenance: n/a

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | C1@160K bubble 0 dew 0; C3@300K bubble 0 dew 0; CO2@250K bubble 0 dew 0; N2@110K bubble 0 dew 0 |
| phase_identification | ok | 0 | C1@160K ok; C3@300K ok |
| round_trip | ok | 2.6e-14 | 350K/3.447e+06Pa T_ph 2.6e-14 H 2.4e-14 T_ps 2.6e-14 |
| dhdT_cp | ok | 5.1e-07 | 350K/3.447e+06Pa vapor cp 46.0626 dH/dT 46.0626 |
| gibbs_duhem | ok | 5.4e-08 | ['C1', 'C3']@250K/5e+06Pa hc_liquid 5.4e-08; ['C1', 'CO2']@250K/2e+06Pa vapor 6.3e-09 |
| single_liquid_limit | ok | 0 | 250K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 350K/3.447e+06Pa |

Note: The slice feed minus the C6+ pseudo-component and water, renormalized: a lumped cut has no CoolProp fluid and is refused by name (consistent with the GERG row and the family's never-silently-approximated rule), and water-bearing light-hydrocarbon mixtures have no verified HEOS interaction parameters — water belongs to the IAPWS rows. K values surface through saturation points and flashes; k_values returns None by design.

### L4 cross-model pairs

- n/a — refuses the slice feed: ComponentNotSupported: CoolPropPackage has no parameters for component(s) ['C6+']; supported: ['C1', 'C2', 'C3', 'CO2', 'H2O', 'H2S', 'N2', 'iC4', 'iC5', 'nC4', 'nC5']

## L1/L2 reference-case outcomes

19/19 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `heos-pure-C1-125K` — coolprop:CH4
- `heos-pure-nC4-280K` — coolprop:n-Butane
- `heos-pure-CO2-265K` — coolprop:CO2
- `heos-c1co2-293.130K-6.135MPa` — Petropoulou, Voutsas, Westman, Austegard, Lovseth & Stang (2018) Fluid Phase Equilib. 462, 44-58, via NIST ThermoML (doi 10.1016/j.fluid.2018.01.011), 293.13 K isotherm; retrieved 2026-10-21
- `heos-c1co2-293.130K-6.976MPa` — Petropoulou, Voutsas, Westman, Austegard, Lovseth & Stang (2018) Fluid Phase Equilib. 462, 44-58, via NIST ThermoML (doi 10.1016/j.fluid.2018.01.011), 293.13 K isotherm; retrieved 2026-10-21

## References

- Bell, I. H., Wronski, J., Quoilin, S., Lemort, V., 'Pure and Pseudo-pure Fluid Thermophysical Property Evaluation and the Open-Source Thermophysical Property Library CoolProp', Ind. Eng. Chem. Res. 53(6), 2498-2508, 2014
- Kunz, O., Wagner, W., 'The GERG-2008 Wide-Range Equation of State for Natural Gases and Other Mixtures', J. Chem. Eng. Data 57, 3032-3091, 2012 (multifluid mixture model provenance; the row evaluates CoolProp's fitted mixture parameters)
