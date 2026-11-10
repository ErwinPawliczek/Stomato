# hf_hexamer — HF-hexamerizing gamma-phi (in-house kernel, Jarry & Davis parameters)

family `special` · status **provisional** · adapter `ngdesign.thermo.special:HFHexamerPackage`.

## Applicability (Carlson 1996)

- component classes: polar_organic, acid_gas
- polar: True · electrolyte: False
- T window: 270–380 K · P window: 1000–500000 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/special/association.yaml
- provenance: In-house chemical-theory vapour, the hoc_dimer construction with the monomer-hexamer equilibrium 6 HF <=> (HF)6 (special.AssociatingGas with n = 6): log10 Kp = a + b/T regressed from saturated-vapour densities by Jarry & Davis (J. Phys. Chem. 57, 600 (1953)), converted from their mmHg pressure basis to Pa; association enthalpy -R b ln10 = -165.8 kJ per mole of hexamer. Schotte (Ind. Eng. Chem. Process Des. Dev. 19, 432 (1980)) is the oligomer-treatment reference for HF vapour association. Liquid ideal on apparent composition with HF's saturation fugacity coefficient (PhiSat basis).

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | HF@280K bubble 0 dew 0; HF@330K bubble 0 dew 0 |
| phase_identification | ok | 0 | HF@280K ok; HF@330K ok |
| round_trip | ok | 9.4e-16 | 300K/20000Pa T_ph 0 H 0 T_ps 0; 360K/100000Pa T_ph 1.6e-16 H 9.4e-16 T_ps 3.2e-16 |
| dhdT_cp | ok | 3.3e-08 | 370K/50000Pa vapor cp 31.5869 dH/dT 31.5869 |
| gibbs_duhem | ok | 5.3e-08 | ['H2O', 'HF']@320K/50000Pa vapor 5.3e-08 |
| single_liquid_limit | ok | 0 | 280K/200000Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 330K/50000Pa |

Note: The liquid is ideal (gamma = 1), so the Gibbs-Duhem check runs on the associated vapour; dhdT_cp runs on the vapour at 370 K / 50 kPa (the liquid also passes at 300 K / 300 kPa: Cp 37.8904 vs dH/dT 37.8903).

## L1/L2 reference-case outcomes

3/3 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `hf-pure-tboil-streng` — NIST Chemistry WebBook (SRD 69), hydrogen fluoride, Phase change data table, T boil = 292.7 K (Streng, J. Chem. Eng. Data 16, 357 (1971); TRC uncertainty 0.25 K); https://webbook.nist.gov/cgi/cbook.cgi?ID=C7664393&Mask=4, retrieved 2026-11-04.
- `hf-pure-psat-278.15K-sheft` — NIST Chemistry WebBook (SRD 69), hydrogen fluoride, Phase change data, Antoine Equation Parameters table (273.17-303.09 K: A 4.9148, B 1556.559, C 24.199; NIST fit to Sheft, Perkins & Hyman, J. Inorg. Nucl. Chem. 35, 3677 (1973), doi:10.1016/0022-1902(73)80055-7), evaluated at 278.15 K; https://webbook.nist.gov/cgi/cbook.cgi?ID=C7664393&Mask=4, retrieved 2026-11-04.
- `hf-pure-psat-298.15K-sheft` — NIST Chemistry WebBook (SRD 69), hydrogen fluoride, Phase change data, Antoine Equation Parameters table (273.17-303.09 K: A 4.9148, B 1556.559, C 24.199; NIST fit to Sheft, Perkins & Hyman, J. Inorg. Nucl. Chem. 35, 3677 (1973), doi:10.1016/0022-1902(73)80055-7), evaluated at 298.15 K; https://webbook.nist.gov/cgi/cbook.cgi?ID=C7664393&Mask=4, retrieved 2026-11-04.
