# psrk — PSRK (SRK + MHV1 over PSRK-UNIFAC, Mathias-Copeman alpha)

family `mixing` · status **provisional** · adapter `ngdesign.thermo.mixing_rules:SRKPSRKThermo`.

## Applicability (Carlson 1996)

- component classes: alcohol, water, hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 1000–5e+07 Pa
- phases: V, L, VLL

## Parameters

- source: PSRK (Predictive Soave-Redlich-Kwong, Holderbaum & Gmehling 1991): SRK with the MHV1 zero-pressure mixing rule (q1 = -0.64663) over the PSRK-UNIFAC residual group model (thermo unifac_psrk variant, PSRKSG/PSRKIP); Mathias-Copeman alpha with the T-02 fits (Coquelet et al. 2004) for the polar components
- provenance: Holderbaum, T. & Gmehling, J., "PSRK: A group contribution equation of state based on UNIFAC", Fluid Phase Equilib. 70(2-3), 251-265, 1991; Michelsen, M. L., "A modified Huron-Vidal mixing rule for cubic equations of state", Fluid Phase Equilib. 60, 213-219, 1990 (MHV1 reference); Mathias, P. M. & Copeman, T. W., Fluid Phase Equilib. 13, 91-108, 1983; k_ij-free form - the gE model carries all interaction information

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | MeOH@300K bubble 0 dew 0; MeOH@350K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | MeOH@300K ok; MeOH@350K ok; H2O@400K ok |
| round_trip | ok | 2.8e-16 | 380K/50000Pa T_ph 1.5e-16 H 0 T_ps 1.5e-16; 400K/100000Pa T_ph 2.8e-16 H 0 T_ps 2.8e-16 |
| dhdT_cp | ok | 7e-08 | 380K/50000Pa vapor cp 42.2408 dH/dT 42.2408 |
| gibbs_duhem | ok | 9e-09 | ['H2O', 'MeOH']@350K/100000Pa aqueous 9e-09; ['H2O', 'MeOH']@380K/50000Pa vapor 7.9e-09 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['hc_liquid'] vf=0.0 |

Note: provisional on L0 only: the 8 bound T-12 cases - 4 L1 pure, 2 L2 MeOH/H2O VLE and the 2 L3 aqueous-methane solubility points (which PASS: methane solubility in water at 13.1/45.0 MPa within the liquid_comp tolerances) - are assessed above; the pure points inherit the untranslated SRK liquid-density limits and the MeOH/H2O points are general group-contribution predictions without a MeOH/H2O-specific parameter fit; promotion needs a PSRK-specific assessment beyond the transferred UNIFAC basis

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C2 (74-84-0) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)

## L1/L2 reference-case outcomes

16/26 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `psrk-pure-MeOH-305K` — coolprop:Methanol
- `psrk-pure-MeOH-330K` — coolprop:Methanol
- `psrk-pure-H2O-340K` — coolprop:Water
- `psrk-pure-H2O-370K` — coolprop:Water
- `psrk-meohh2o-101.325kPa-349.05K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `psrk-meohh2o-312.91K-20.705kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20
- `psrk-c1h2o-310.9K-13.10MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 31, 100 F isotherm; retrieved 2026-10-20
- `psrk-c1h2o-310.9K-44.99MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 31, 100 F isotherm; retrieved 2026-10-20

## References

- Holderbaum, T. & Gmehling, J., Fluid Phase Equilib. 70(2-3), 251-265, 1991
- Michelsen, M. L., Fluid Phase Equilib. 60, 213-219, 1990
- Mathias, P. M. & Copeman, T. W., Fluid Phase Equilib. 13, 91-108, 1983
