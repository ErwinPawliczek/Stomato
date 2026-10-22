# henry-sander — Henry's law for the dilute light gases (Sander-compiled pure-water sets) + Raoult

family `kvalue` · status **validated** · adapter `ngdesign.thermo.kvalue:HenryIdealThermo`.

## Applicability (Carlson 1996)

- component classes: light_gas, water, acid_gas
- polar: True · electrolyte: False
- T window: 273–373 K · P window: 100000–1e+07 Pa
- phases: V, L, VLL

## Parameters

- source: Henry constants under data/thermo_params/kvalue/henry.yaml; water Psat from the ChemSep databank
- provenance: methane from Lekvam, K. & Bishnoi, P. R., 'Dissolution of methane in water at low temperatures and intermediate pressures', Fluid Phase Equilib. 131, 297-309, 1997, as compiled in Sander 2015 (the Sander methane note-71 entry is seawater and was rejected); CO2 from Versteeg, G. F. & van Swaaij, W. P. M., 'Solubility and Diffusivity of Acid Gases in Aqueous Alkanolamine Solutions', J. Chem. Eng. Data 33(1), 29-34, 1988; Raoult for the non-solute components

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 2.2e-16 | C1@125K bubble 0 dew 0; C3@300K bubble 0 dew 1.2e-16; nC4@280K bubble 2.2e-16 dew 0; CO2@265K bubble 0 dew 0 |
| phase_identification | ok | 0 | C1@125K ok; H2O@300K ok |
| round_trip | ok | 0 | 300K/10000Pa T_ph 0 H 0 T_ps 0 |
| dhdT_cp | ok | 7.7e-08 | 300K/10000Pa vapor cp 33.7702 dH/dT 33.7702 |
| single_liquid_limit | ok | 0 | 300K/5e+06Pa kinds=['aqueous'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 300K/100000Pa |

Declared exclusions (not silent skips):

- `gibbs_duhem` — K_i = H_i/P for the dilute solutes and Psat_i/P for water, both composition-independent: the Gibbs-Duhem residual is identically zero by construction and the check's |sum x dlnphi| / sum |x dlnphi| normalisation degenerates to 0/0

## L1/L2 reference-case outcomes

10/10 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `henry-sander-pureK-C1-125K` — coolprop:CH4 - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `henry-sander-pureK-C3-300K` — coolprop:Propane - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `henry-sander-pureK-nC4-280K` — coolprop:n-Butane - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `henry-sander-pureK-CO2-265K` — coolprop:CO2 - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `henry-sander-c1h2o-298.2K-4.54MPa` — Culberson & McKetta, methane in water, J. Petrol. Technol., vol. 3, p. 223, 1951, as compiled in the IUPAC Solubility Data Series vol. 27/28 (Methane), pp. 31-32, https://iupac.github.io/SolubilityDataSeries/volumes/SDS-27-28.pdf; x_C1 0.001000 at 4.54 MPa; retrieved 2026-10-21
- `henry-sander-c1h2o-310.9K-6.55MPa` — Culberson & McKetta, methane in water, J. Petrol. Technol., vol. 3, p. 223, 1951, as compiled in the IUPAC Solubility Data Series vol. 27/28 (Methane), pp. 31-32, https://iupac.github.io/SolubilityDataSeries/volumes/SDS-27-28.pdf; x_C1 0.001123 at 6.55 MPa; retrieved 2026-10-21

## References

- Sander, R., 'Compilation of Henry's law constants (version 4.0) for water as solvent', Atmos. Chem. Phys. 15, 4399-4981, 2015
- Lekvam, K. & Bishnoi, P. R., Fluid Phase Equilib. 131, 297-309, 1997
- Culberson, O. L. & McKetta, J. J., 'Phase Equilibria in Hydrocarbon-Water Systems III - The Solubility of Methane in Water at Pressures to 10,000 psia', J. Petrol. Technol. 3(5), 223, 1951
