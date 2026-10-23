# multifluid — Multi-fluid Helmholtz (teqp CoolProp library)

family `saft` · status **provisional** · adapter `ngdesign.thermo.teqp_bridge:MultifluidThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert, acid_gas
- polar: False · electrolyte: False
- T window: 60–800 K · P window: 100–1e+08 Pa
- phases: V, L

## Parameters

- source: teqp multifluid over the CoolProp fluid library (data/thermo_params/saft/pure.yaml alias table)
- provenance: fluid names resolve to teqp's bundled CoolProp-32 fluid library (IAPWS, NIST REFPROP-derived and GERG Helmholtz formulations as shipped by teqp 0.23.2); binary pairs and departure functions from teqp's bundled mixture files. Water-bearing feeds are refused — teqp's bundled pair file has no water interaction data (bare Lorentz-Berthelot), which puts the slice dew 2x above the CoolProp with-water value

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | C1@150K bubble 0 dew 0; C2@200K bubble 0 dew 0; N2@90K bubble 0 dew 0; CO2@240K bubble 0 dew 0 |
| phase_identification | ok | 0 | C1@150K ok; C3@250K ok |
| round_trip | ok | 1.8e-07 | 150K/3e+06Pa T_ph 1.3e-07 H 1.1e-07 T_ps 8.9e-08; 200K/300000Pa T_ph 9.1e-08 H 1.8e-07 T_ps 1.4e-07 |
| dhdT_cp | ok | 0 | 200K/300000Pa vapor cp 33.8666 dH/dT 33.8666 |
| gibbs_duhem | ok | 7.1e-09 | ['C1', 'N2']@200K/500000Pa vapor 1.4e-09; ['C1', 'N2']@150K/3e+06Pa hc_liquid 7.1e-09 |
| single_liquid_limit | ok | 0 | 150K/3e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 200K/500000Pa |

### L4 cross-model pairs

- n/a — refuses the slice feed: SaftParameterError: no verified multifluid parameters for ['H2O']; supported: ['C1', 'C2', 'C3', 'C6+', 'CO2', 'N2', 'iC4', 'iC5', 'nC4', 'nC5'] (unsupported components are refused, never treated as ideal)

## L1/L2 reference-case outcomes

6/7 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `c1co2-293.130K-6.135MPa` — Petropoulou, Voutsas, Westman, Austegard, Lovseth & Stang (2018) Fluid Phase Equilib. 462, 44-58, via NIST ThermoML, doi 10.1016/j.fluid.2018.01.011, 293.13 K isotherm; retrieved 2026-10-21
- `c1n2-149.989K-2.908MPa` — Janisch, Raabe & Kohler (2007) J. Chem. Eng. Data 52, 1897-1903, via NIST ThermoML (doi 10.1021/je700210n), CH4+N2 149.989 K isotherm; retrieved 2026-10-21
- `aga8-c1n2-134.02K-dew` — AGA Report No. 8 Part 1&2 supplementary test data tables (NIST AGA8 distribution, pages.nist.gov/AGA8, Test Data.xls, Binary Mixture Calculations sheet, GERG-2008 column, methane/nitrogen 50/50 mol %); retrieved 2026-10-21
- `aga8-c1n2-146.37K-dew` — AGA Report No. 8 Part 1&2 supplementary test data tables (NIST AGA8 distribution, pages.nist.gov/AGA8, Test Data.xls, Binary Mixture Calculations sheet, GERG-2008 column, methane/nitrogen 50/50 mol %); retrieved 2026-10-21
- `aga8-c1n2-153.41K-dew` — AGA Report No. 8 Part 1&2 supplementary test data tables (NIST AGA8 distribution, pages.nist.gov/AGA8, Test Data.xls, Binary Mixture Calculations sheet, GERG-2008 column, methane/nitrogen 50/50 mol %); retrieved 2026-10-21

## References

- teqp 0.23 (Thol & Bell), https://teqp.readthedocs.io, MIT licence
- Huber, Lemmon, Diky, Smith & Brunner, "ThermoData Engine (TDE103b)", J. Chem. Eng. Data 61 (2016) 3382-3395 (CoolProp fluid data lineage)
