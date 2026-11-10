# eos_cg — EOS-CG combustion-gas mixture model (2016)

family `helmholtz` · status **validated** · adapter `ngdesign.thermo.helmholtz:EosCgPackage`.

## Applicability (Carlson 1996)

- component classes: light_gas, inert, acid_gas, water
- polar: True · electrolyte: False
- T window: 250–1000 K · P window: 1000–1e+08 Pa
- phases: V, L

## Parameters

- source: CoolProp 8.0.0 HEOS binary table (MIT), the pairs citing Gernert's 2013 thesis
- provenance: All 15 pairs of CO2, H2O, N2, O2, Ar and CO in the installed CoolProp cite Gernert-Thesis-2013, with the departure functions CO2-H2O, GeneralizedAirWater and Ar-CO2, over the reference pure-fluid equations; that is the Gernert & Span (2016) model. Checked 2026-11-01. The 2016 paper itself is paywalled; EOS-CG-2021 (Neumann et al. 2023, CC BY 4.0) is open but is a different parameter set, which CoolProp does not carry yet (PR 3281 open when checked).

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | CO2@250K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | CO2@250K ok; H2O@350K ok |
| round_trip | ok | 2.1e-14 | 350K/5e+06Pa T_ph 2.1e-14 H 1.7e-14 T_ps 2.1e-14 |
| dhdT_cp | ok | 2.8e-06 | 350K/5e+06Pa vapor cp 49.0662 dH/dT 49.0663 |
| gibbs_duhem | ok | 8.2e-08 | ['CO2', 'N2']@350K/5e+06Pa vapor 8.2e-08 |
| single_liquid_limit | ok | 0 | 250K/2e+07Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 350K/5e+06Pa |

Note: The refusal this row used to carry said teqp and CoolProp ship no EOS-CG files; rechecking on 2026-11-01 found the 2016 pairs in both. On CO2, H2O and N2 the row computes what coolprop_heos computes; it exists to admit O2, Ar and CO and to refuse everything else. The round trip runs on pure CO2 because CoolProp's PQ solver fails on CO2 + N2 at the bubble-temperature step of the shared PH/PS flash (measured at 350 K, 1 and 5 MPa); since 2026-11-04 a PH/PS flash with no reachable boundary at P falls back to inverting flash_pt. The near-critical Westman CO2 + N2 bubble points (298.161 K/7.1003 MPa, 298.162 K/7.4191 MPa) that raised SaturationError solve since 2026-11-09 (composition continuation) and pass at +0.01 / -0.03 % (helm-co2n2-*-bubble); the 269.997 K/9.5571 MPa dew point (y_CO2 0.58169) lies below the model's lowest dew-curve CO2 fraction at that T (about 0.5822), so it has no dew point here.

### L4 cross-model pairs

- n/a — refuses the slice feed: ComponentNotSupported: EosCgPackage has no parameters for component(s) ['C1', 'C2', 'C3', 'C6+', 'iC4', 'iC5', 'nC4', 'nC5']; supported: ['Ar', 'CO', 'CO2', 'H2O', 'N2', 'O2']

## L1/L2 reference-case outcomes

6/6 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `helm-co2n2-298.161K-7.100MPa-bubble` — Westman, S. F., Stang, H. G. J., Lovseth, S. W., Austegard, A., Snustad, I., Storset, S. O., Ertesvag, I. S., "Vapor-liquid equilibrium data for the carbon dioxide and nitrogen (CO2+N2) system at the temperatures 223, 270, 298 and 303 K and pressures up to 18 MPa", Fluid Phase Equilib. 409, 207-241, 2016, doi:10.1016/j.fluid.2015.09.034; NIST TRC ThermoML archive record https://trc.nist.gov/ThermoML/10.1016/j.fluid.2015.09.034.xml, PureOrMixtureData dataset 2 (liquid-phase CO2 mole fraction), T = 298.161 K, p = 7100.3 kPa, CO2 mole fraction 0.98384 (U 0.00056); retrieved 2026-11-09
- `helm-co2n2-298.162K-7.419MPa-bubble` — Westman, S. F., Stang, H. G. J., Lovseth, S. W., Austegard, A., Snustad, I., Storset, S. O., Ertesvag, I. S., "Vapor-liquid equilibrium data for the carbon dioxide and nitrogen (CO2+N2) system at the temperatures 223, 270, 298 and 303 K and pressures up to 18 MPa", Fluid Phase Equilib. 409, 207-241, 2016, doi:10.1016/j.fluid.2015.09.034; NIST TRC ThermoML archive record https://trc.nist.gov/ThermoML/10.1016/j.fluid.2015.09.034.xml, PureOrMixtureData dataset 2 (liquid-phase CO2 mole fraction), T = 298.162 K, p = 7419.1 kPa, CO2 mole fraction 0.97525 (U 0.00057); retrieved 2026-11-09
- `eoscg-co2-psat-298.174K` — Westman, S. F., Stang, H. G. J., Lovseth, S. W., Austegard, A., Snustad, I., Storset, S. O., Ertesvag, I. S., "Vapor-liquid equilibrium data for the carbon dioxide and nitrogen (CO2+N2) system at the temperatures 223, 270, 298 and 303 K and pressures up to 18 MPa", Fluid Phase Equilib. 409, 207-241, 2016, doi:10.1016/j.fluid.2015.09.034; NIST TRC ThermoML archive record https://trc.nist.gov/ThermoML/10.1016/j.fluid.2015.09.034.xml, PureOrMixtureData dataset 0 (pure CO2 vapour pressure), T = 298.174 K, p = 6436.9 kPa; retrieved 2026-11-04
- `eoscg-co2-psat-303.158K` — Westman, S. F., Stang, H. G. J., Lovseth, S. W., Austegard, A., Snustad, I., Storset, S. O., Ertesvag, I. S., "Vapor-liquid equilibrium data for the carbon dioxide and nitrogen (CO2+N2) system at the temperatures 223, 270, 298 and 303 K and pressures up to 18 MPa", Fluid Phase Equilib. 409, 207-241, 2016, doi:10.1016/j.fluid.2015.09.034; NIST TRC ThermoML archive record https://trc.nist.gov/ThermoML/10.1016/j.fluid.2015.09.034.xml, PureOrMixtureData dataset 0 (pure CO2 vapour pressure), T = 303.158 K, p = 7210.5 kPa; retrieved 2026-11-04
- `eoscg-co2n2-269.996K-9.582MPa-bubble` — Westman, S. F., Stang, H. G. J., Lovseth, S. W., Austegard, A., Snustad, I., Storset, S. O., Ertesvag, I. S., "Vapor-liquid equilibrium data for the carbon dioxide and nitrogen (CO2+N2) system at the temperatures 223, 270, 298 and 303 K and pressures up to 18 MPa", Fluid Phase Equilib. 409, 207-241, 2016, doi:10.1016/j.fluid.2015.09.034; NIST TRC ThermoML archive record https://trc.nist.gov/ThermoML/10.1016/j.fluid.2015.09.034.xml, PureOrMixtureData dataset 1 (liquid-phase CO2 mole fraction), T = 269.996 K, p = 9582.4 kPa, CO2 mole fraction 0.86046; retrieved 2026-11-04
- `eoscg-co2n2-298.162K-7.099MPa-dew` — Westman, S. F., Stang, H. G. J., Lovseth, S. W., Austegard, A., Snustad, I., Storset, S. O., Ertesvag, I. S., "Vapor-liquid equilibrium data for the carbon dioxide and nitrogen (CO2+N2) system at the temperatures 223, 270, 298 and 303 K and pressures up to 18 MPa", Fluid Phase Equilib. 409, 207-241, 2016, doi:10.1016/j.fluid.2015.09.034; NIST TRC ThermoML archive record https://trc.nist.gov/ThermoML/10.1016/j.fluid.2015.09.034.xml, PureOrMixtureData dataset 2 (gas-phase CO2 mole fraction), T = 298.162 K, p = 7098.8 kPa, CO2 mole fraction 0.95952; retrieved 2026-11-04

## References

- Gernert, J., Span, R., 'EOS-CG: A Helmholtz energy mixture model for humid combustion gases and CCS mixtures', J. Chem. Thermodyn. 93, 274-293, 2016
- Bell, I. H. et al., Ind. Eng. Chem. Res. 53(6), 2498-2508, 2014 (CoolProp)
