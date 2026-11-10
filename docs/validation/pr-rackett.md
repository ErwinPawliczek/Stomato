# pr-rackett — Peng-Robinson, Rackett liquid density

family `cubic` · status **validated** · adapter `ngdesign.thermo.cubic:PrRackettThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert
- polar: False · electrolyte: False
- T window: 90–700 K · P window: 1000–2e+08 Pa
- phases: V, L, VLL

## Parameters

- source: thermo IPDB (ChemSep) for VLE; the correlation is generalised and carries no fitted parameters
- provenance: Kooijman & Taylor, ChemSep IPDB; critical constants, critical volumes and acentric factors from the ChemSep pure-component database; binary interaction parameters from the 'ChemSep PR' table, 0 where the table has no pair

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | C1@160K bubble 0 dew 0; C3@300K bubble 0 dew 0; nC4@300K bubble 0 dew 0; H2O@400K bubble 0 dew 0 |
| phase_identification | ok | 0 | nC4@300K ok; C3@300K ok; H2O@300K ok |
| round_trip | ok | 4.9e-16 | 350K/3.447e+06Pa T_ph 0 H 0 T_ps 4.9e-16 |
| dhdT_cp | ok | 4.7e-07 | 350K/3.447e+06Pa vapor cp 47.62 dH/dT 47.6201 |
| gibbs_duhem | ok | 2e-07 | ['C1', 'C3']@250K/2e+06Pa hc_liquid 2e-07; ['C1', 'CO2']@250K/2e+06Pa vapor 2.7e-09 |
| single_liquid_limit | ok | 0 | 250K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 350K/3.447e+06Pa |

Note: VLE, enthalpy and entropy are the base row's; only the volume of liquid roots changes, so the L0 checks exercise the base row's surface. The reported liquid volume is a correlation and is not the pressure derivative of the EOS Gibbs energy.

## L1/L2 reference-case outcomes

22/23 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `cubicopt-pure-C1-125K` — coolprop:CH4
- `cubicopt-pure-C3-300K` — coolprop:Propane
- `cubicopt-pure-nC4-280K` — coolprop:n-Butane
- `cubicopt-pure-CO2-265K` — coolprop:CO2
- `cubicopt-c1c3-294.26K-6.895MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20
- `cubicopt-c1co2-277.15K-5.97MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20

## References

- Spencer, C. F.; Danner, R. P. J. Chem. Eng. Data 1972, 17, 236; Yamada, T.; Gunn, R. D. J. Chem. Eng. Data 1973, 18, 234; Rackett, H. G. J. Chem. Eng. Data 1970, 15, 514
