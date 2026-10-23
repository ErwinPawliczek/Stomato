# gerg2008_teqp — GERG-2008 (teqp multi-fluid, exact parameters)

family `saft` · status **provisional** · adapter `ngdesign.thermo.teqp_bridge:Gerg2008TeqpThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert, acid_gas
- polar: False · electrolyte: False
- T window: 60–800 K · P window: 100–1e+08 Pa
- phases: V, L

## Parameters

- source: teqp multifluid over teqp's bundled fluid library with the Kunz & Wagner (2012) GERG-2008 reducing/departure parameters (data/thermo_params/saft/pure.yaml gerg2008_teqp alias table)
- provenance: same teqp 0.23.2 bundled fluid library as the multifluid row; the natural-gas binary pairs and departure functions carry Kunz-JCED-2012 citations in teqp's mixture files. This row is the exact-backend cross-check the T-04 `gerg2008` row (CoolProp's fitted pure-fluid tables) defers to (issue

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

- n/a — refuses the slice feed: SaftParameterError: no verified gerg2008_teqp parameters for ['H2O']; supported: ['C1', 'C2', 'C3', 'C6+', 'CO2', 'N2', 'iC4', 'iC5', 'nC4', 'nC5'] (unsupported components are refused, never treated as ideal)

## L1/L2 reference-case outcomes

5/7 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `c1n2-130.079K-0.614MPa` — Janisch, Raabe & Kohler (2007) J. Chem. Eng. Data 52, 1897-1903, via NIST ThermoML (doi 10.1021/je700210n), CH4+N2 130.079 K isotherm; retrieved 2026-10-21
- `c1n2-149.989K-2.908MPa` — Janisch, Raabe & Kohler (2007) J. Chem. Eng. Data 52, 1897-1903, via NIST ThermoML (doi 10.1021/je700210n), CH4+N2 149.989 K isotherm; retrieved 2026-10-21
- `aga8-c1n2-134.02K-dew` — AGA Report No. 8 Part 1&2 supplementary test data tables (NIST AGA8 distribution, pages.nist.gov/AGA8, Test Data.xls, Binary Mixture Calculations sheet, GERG-2008 column, methane/nitrogen 50/50 mol %); retrieved 2026-10-21
- `aga8-c1n2-146.37K-dew` — AGA Report No. 8 Part 1&2 supplementary test data tables (NIST AGA8 distribution, pages.nist.gov/AGA8, Test Data.xls, Binary Mixture Calculations sheet, GERG-2008 column, methane/nitrogen 50/50 mol %); retrieved 2026-10-21
- `aga8-c1n2-153.41K-dew` — AGA Report No. 8 Part 1&2 supplementary test data tables (NIST AGA8 distribution, pages.nist.gov/AGA8, Test Data.xls, Binary Mixture Calculations sheet, GERG-2008 column, methane/nitrogen 50/50 mol %); retrieved 2026-10-21

## References

- Kunz & Wagner, "The GERG-2008 Wide-Range Equation of State for Natural Gases and Other Mixtures", J. Chem. Eng. Data 57 (2012) 3032-3091
- teqp 0.23 (Thol & Bell), https://teqp.readthedocs.io, MIT licence
