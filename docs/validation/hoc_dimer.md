# hoc_dimer — Dimerizing-acid gamma-phi (Hayden-O'Connell family, in-house kernel)

family `special` · status **provisional** · adapter `ngdesign.thermo.special:HaydenOConnellDimerPackage`.

## Applicability (Carlson 1996)

- component classes: polar_organic, acid_gas
- polar: True · electrolyte: False
- T window: 290–400 K · P window: 1000–200000 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/special/association.yaml
- provenance: In-house chemical-theory vapour (Marek & Standart, Collect. Czech. Chem. Commun. 19, 1074 (1954); Prausnitz, Lichtenthaler & de Azevedo, Molecular Thermodynamics of Fluid-Phase Equilibria, 3rd ed., sec. 5.8-5.9): monomer, dimer and every non-associating component form an ideal-gas mixture in dimerization equilibrium Kp = p_D/p_M^2; the apparent fugacity of the acid is its monomer partial pressure, the non-associating components get phi = 1/Z, and H carries xi dH (dimers per apparent mole x association enthalpy). Acetic-acid parameters from Ritter & Simons, J. Am. Chem. Soc. 67, 757 (1945): log10 K2 = 3164/T - 10.4184 (mmHg^-1), dH = -3164 R ln10 = -60.57 kJ/mol (verified via Sebastiani & Lacquaniti, Chem. Eng. Sci. 22, 1155 (1967); data/thermo_params/special/association.yaml). Liquid: ideal on apparent composition with the saturation fugacity coefficient of the acid (f_L = x phi_sat Psat, phi_sat the pure chemical-theory vapour at (T, Psat)), so a pure acid boils exactly at its databank Psat and the latent heat obeys Clapeyron with the associated vapour's Z. The curated nrtl_hoc / nrtl_nothnagel rows keep refusing acid-strength slates and point here.

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | AcOH@330K bubble 0 dew 0; AcOH@380K bubble 0 dew 0 |
| phase_identification | ok | 0 | AcOH@330K ok; AcOH@380K ok |
| round_trip | ok | 3.3e-14 | 365K/50000Pa T_ph 0 H 0 T_ps 0; 400K/100000Pa T_ph 5.7e-16 H 3.3e-14 T_ps 1.4e-16 |
| dhdT_cp | ok | 1.5e-05 | 400K/50000Pa vapor cp 181.125 dH/dT 181.122 |
| gibbs_duhem | ok | 5.8e-09 | ['AcOH', 'H2O']@400K/50000Pa vapor 5.8e-09 |
| single_liquid_limit | ok | 0 | 330K/100000Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 390K/50000Pa |

Note: The liquid is ideal (gamma = 1), so the Gibbs-Duhem check runs on the associated vapour, where the apparent ln phi are not trivial; the liquid's identity holds by construction.

## L1/L2 reference-case outcomes

13/95 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `acoh-pure-tboil-nist` — NIST Chemistry WebBook (SRD 69), acetic acid, Phase change data table, T boil = 391.2 +/- 0.6 K (AVG of 80 of 90 values); https://webbook.nist.gov/cgi/cbook.cgi?ID=C64197&Mask=4, retrieved 2026-11-04.
- `acoh-pure-psat-320K-mcdonald` — NIST Chemistry WebBook (SRD 69), acetic acid, Phase change data, Antoine Equation Parameters table (290.26-391.01 K: A 4.68206, B 1642.54, C -39.764; NIST fit to McDonald, Shrader et al. 1959), evaluated at 320.0 K; https://webbook.nist.gov/cgi/cbook.cgi?ID=C64197&Mask=4, retrieved 2026-11-04.
- `acoh-pure-psat-360K-mcdonald` — NIST Chemistry WebBook (SRD 69), acetic acid, Phase change data, Antoine Equation Parameters table (290.26-391.01 K: A 4.68206, B 1642.54, C -39.764; NIST fit to McDonald, Shrader et al. 1959), evaluated at 360.0 K; https://webbook.nist.gov/cgi/cbook.cgi?ID=C64197&Mask=4, retrieved 2026-11-04.
