# depg_henry — Physical solvent (DEPG Selexol-type) Henry solubility at 25 C

family `kvalue` · status **provisional** · adapter `ngdesign.thermo.kvalue:DepgHenryThermo`.

## Applicability (Carlson 1996)

- component classes: acid_gas, light_gas, polar_organic
- polar: True · electrolyte: False
- T window: 293.15–303.15 K · P window: 10000–1e+07 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/kvalue/depg.yaml
- provenance: Burr & Lyddon solubilities of CO2, H2S, CH4, CO, H2 and N2 in DEPG (Bucklin & Schendel 1984 data) at 25 C and 1 atm, read as Henry constants; gamma = 1. Tetraglyme is the stream component standing in for the DEPG mixture. No temperature dependence is available openly, so the flash refuses outside 293.15-303.15 K

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| round_trip | ok | 9.1e-14 | 298.15K/2e+06Pa T_ph 1.5e-15 H 9.8e-15 T_ps 9.1e-14 |
| dhdT_cp | ok | 8.1e-09 | 298.15K/100000Pa vapor cp 173.664 dH/dT 173.664 |
| single_liquid_limit | ok | 0 | 298.15K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 298.15K/1e+06Pa |

Declared exclusions (not silent skips):

- `gibbs_duhem` — the K-values are composition-independent, so the residual is identically zero and the check's normalisation degenerates to 0/0, as for braun-k10
- `phase_identification` — same basis as pure_psat_limit
- `pure_psat_limit` — the row refuses a feed with no gas solubility data and the solvent's Psat is about 0.1 Pa, below its pressure window; the claimed surface is gas in solvent

### L4 cross-model pairs

- n/a — refuses the slice feed: SaturationError: kvalue saturation at T=293.15 K: Lee-Kesler two-phase region collapses before K crosses unity

## L1/L2 reference-case outcomes

1/3 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `depg-tetraglyme-C1-298.15K` — de la Iglesia, O., Mainar, A. M., Pardo, J. I., Urieta, J. S., 'Solubilities of Nonpolar Gases in Triethylene Glycol Dimethyl Ether, Tetraethylene Glycol Dimethyl Ether, Dimethyl Carbonate, and Diethyl Carbonate at 298.15 K and 101.33 kPa Partial Pressure of Gas', J. Chem. Eng. Data 48, 657-661, 2003, doi:10.1021/je020199q; NIST TRC ThermoML record https://trc.nist.gov/ThermoML/10.1021/je020199q.xml, PureOrMixtureData dataset 19 (methane + 2,5,8,11,14-pentaoxapentadecane), x_methane = 0.002548 at 298.15 K, 101.33 kPa; retrieved 2026-11-04
- `depg-tetraglyme-N2-298.15K` — de la Iglesia, O., Mainar, A. M., Pardo, J. I., Urieta, J. S., 'Solubilities of Nonpolar Gases in Triethylene Glycol Dimethyl Ether, Tetraethylene Glycol Dimethyl Ether, Dimethyl Carbonate, and Diethyl Carbonate at 298.15 K and 101.33 kPa Partial Pressure of Gas', J. Chem. Eng. Data 48, 657-661, 2003, doi:10.1021/je020199q; NIST TRC ThermoML record https://trc.nist.gov/ThermoML/10.1021/je020199q.xml, PureOrMixtureData dataset 18 (nitrogen + 2,5,8,11,14-pentaoxapentadecane), x_nitrogen = 0.0005719 at 298.15 K, 101.33 kPa; retrieved 2026-11-04
- `depg-tetraglyme-H2-298.15K` — de la Iglesia, O., Mainar, A. M., Pardo, J. I., Urieta, J. S., 'Solubilities of Nonpolar Gases in Triethylene Glycol Dimethyl Ether, Tetraethylene Glycol Dimethyl Ether, Dimethyl Carbonate, and Diethyl Carbonate at 298.15 K and 101.33 kPa Partial Pressure of Gas', J. Chem. Eng. Data 48, 657-661, 2003, doi:10.1021/je020199q; NIST TRC ThermoML record https://trc.nist.gov/ThermoML/10.1021/je020199q.xml, PureOrMixtureData dataset 17 (hydrogen + 2,5,8,11,14-pentaoxapentadecane), x_hydrogen = 0.0003726 at 298.15 K, 101.33 kPa; retrieved 2026-11-04

## References

- Burr, B. & Lyddon, L., A Comparison of Physical Solvents for Acid Gas Removal, Bryan Research & Engineering
