# gerg2008_teqp — GERG-2008 (teqp multi-fluid, exact parameters)

family `saft` · status **validated** · adapter `ngdesign.thermo.teqp_bridge:Gerg2008TeqpThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert, acid_gas
- polar: False · electrolyte: False
- T window: 60–800 K · P window: 100–1e+08 Pa
- phases: V, L

## Parameters

- source: teqp 0.23.2 `GERG2008resid` model kind — the Kunz & Wagner (2012) GERG-2008 formulation (data/thermo_params/saft/pure.yaml gerg2008_teqp alias table)
- provenance: GERG-2008's own pure-fluid residual equations plus its binary reducing and departure parameters, as implemented in teqp (verified 2026-11-04 to reproduce the NIST AGA8 GERG-2008 check value p(134.02 K, 1 mol/l, 50/50 C1/N2) = 953319.19 Pa to 1e-6). Until 2026-11-04 the row ran teqp's multi-fluid builder over the CoolProp fluid library (reference-EOS pure fluids), i.e. not GERG-2008. This row is the exact-backend cross-check the T-04 `gerg2008` row (CoolProp's fitted pure-fluid tables) defers to (issue

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | C1@150K bubble 0 dew 0; C2@200K bubble 0 dew 0; N2@90K bubble 0 dew 0; CO2@240K bubble 0 dew 0 |
| phase_identification | ok | 0 | C1@150K ok; C3@250K ok |
| round_trip | ok | 2.5e-07 | 150K/3e+06Pa T_ph 1.2e-07 H 9.7e-08 T_ps 1.2e-07; 200K/300000Pa T_ph 1.3e-07 H 2.5e-07 T_ps 8.7e-08 |
| dhdT_cp | ok | 0 | 200K/300000Pa vapor cp 33.875 dH/dT 33.875 |
| gibbs_duhem | ok | 1.6e-08 | ['C1', 'N2']@200K/500000Pa vapor 1e-08; ['C1', 'N2']@150K/3e+06Pa hc_liquid 1.6e-08 |
| single_liquid_limit | ok | 0 | 150K/3e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 200K/500000Pa |

### L4 cross-model pairs

- n/a — refuses the slice feed: SaftParameterError: no verified gerg2008_teqp parameters for ['H2O']; supported: ['C1', 'C2', 'C3', 'C6+', 'CO2', 'N2', 'iC4', 'iC5', 'nC4', 'nC5'] (unsupported components are refused, never treated as ideal)

## L1/L2 reference-case outcomes

50/51 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `cpv-C1-125.0K` — coolprop:CH4
- `cpv-C1-155.0K` — coolprop:CH4
- `cpv-CO2-240.0K` — coolprop:CO2
- `cpv-CO2-265.0K` — coolprop:CO2
- `cpv-CO2-285.0K` — coolprop:CO2
- `cpv-CO2-288.9K` — coolprop:CO2
- `cpv-nC4-300.0K` — coolprop:n-Butane
- `cpv-nC6-350.0K` — coolprop:n-Hexane
- `c1n2-130.079K-0.614MPa` — Janisch, Raabe & Kohler (2007) J. Chem. Eng. Data 52, 1897-1903, via NIST ThermoML (doi 10.1021/je700210n), CH4+N2 130.079 K isotherm; retrieved 2026-10-21
- `c1n2-149.989K-2.908MPa` — Janisch, Raabe & Kohler (2007) J. Chem. Eng. Data 52, 1897-1903, via NIST ThermoML (doi 10.1021/je700210n), CH4+N2 149.989 K isotherm; retrieved 2026-10-21
- `aga8-c1n2-134.02K-dew` — AGA Report No. 8 Part 1&2 supplementary test data tables (NIST AGA8 distribution, pages.nist.gov/AGA8, Test Data.xls, Binary Mixture Calculations sheet, GERG-2008 column, methane/nitrogen 50/50 mol %); retrieved 2026-10-21
- `aga8-c1n2-146.37K-dew` — AGA Report No. 8 Part 1&2 supplementary test data tables (NIST AGA8 distribution, pages.nist.gov/AGA8, Test Data.xls, Binary Mixture Calculations sheet, GERG-2008 column, methane/nitrogen 50/50 mol %); retrieved 2026-10-21
- `aga8-c1n2-153.41K-dew` — AGA Report No. 8 Part 1&2 supplementary test data tables (NIST AGA8 distribution, pages.nist.gov/AGA8, Test Data.xls, Binary Mixture Calculations sheet, GERG-2008 column, methane/nitrogen 50/50 mol %); retrieved 2026-10-21
- `c1co2-293.130K-6.976MPa` — Petropoulou, Voutsas, Westman, Austegard, Lovseth & Stang (2018) Fluid Phase Equilib. 462, 44-58, via NIST ThermoML, doi 10.1016/j.fluid.2018.01.011, 293.13 K isotherm; retrieved 2026-10-21
- `c1co2-298.142K-6.976MPa` — Petropoulou, Voutsas, Westman, Austegard, Lovseth & Stang (2018) Fluid Phase Equilib. 462, 44-58, via NIST ThermoML, doi 10.1016/j.fluid.2018.01.011, 298.14 K isotherm; retrieved 2026-10-21

## References

- Kunz & Wagner, "The GERG-2008 Wide-Range Equation of State for Natural Gases and Other Mixtures", J. Chem. Eng. Data 57 (2012) 3032-3091
- teqp 0.23 (Thol & Bell), https://teqp.readthedocs.io, MIT licence
