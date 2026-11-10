# soft_saft — soft-SAFT (teqp)

family `saft` · status **validated** · adapter `ngdesign.thermo.teqp_bridge:SoftSaftThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, acid_gas
- polar: False · electrolyte: False
- T window: 90–800 K · P window: 1000–1e+08 Pa
- phases: V, L

## Parameters

- source: teqp 0.23.2 SoftSAFT kind, explicit coefficients (data/thermo_params/saft/pure.yaml)
- provenance: m, sigma, epsilon/k from J. C. Pamies, "Bulk and interfacial properties of chain fluids: a molecular modelling approach", PhD thesis, Universitat Rovira i Virgili (2003), open access (repositori.urv.cat TDX:304; TDX handle 10803/8522): Table 4.1 (PV set, methane to n-octane; Pamies & Vega, Ind. Eng. Chem. Res. 40 (2001) 2532), Table 4.6 (H2, n-C10, n-C16) and Table 4.10 (CO2, non-associating). The engine is teqp's SoftSAFT kind: Johnson, Zollweg & Gubbins (1993) LJ MBWR reference (teqp's x_1..x_32 checked against the paper's Table 10; the EOS reproduces the paper's imposed critical point T* = 1.313, rho* = 0.310) plus the TPT1 chain term with the Johnson, Muller & Gubbins (1994) contact-value fit, the equations of the thesis (eqs 2.2-2.7, A.20-A.26). Unlike pairs use Lorentz-Berthelot with eta = xi = 1 (teqp exposes no binary parameter for this kind); no association. Licences deferred (orchestrator, 2026-11-04); recorded anyway — LICENCE NOT VERIFIED (orchestrator, 2026-11-03): the thesis PDF carries no rights statement and tdx.cat refused automated access (HTTP 403), so the TDX terms of use were not read; TDX theses are commonly limited to private research and teaching use. The Table 4.1 set is also the published Pamies & Vega (2001) set. Review the licence before this row ships in a commercial build.

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | nC4@300K bubble 0 dew 0; nC6@350K bubble 0 dew 0; CO2@250K bubble 0 dew 0 |
| phase_identification | ok | 0 | nC4@300K ok; nC8@400K ok |
| round_trip | ok | 6.9e-07 | 300K/2e+06Pa T_ph 8.5e-08 H 1.7e-07 T_ps 1.3e-07; 350K/200000Pa T_ph 8.9e-08 H 6.9e-07 T_ps 1.2e-07 |
| dhdT_cp | ok | 0 | 350K/200000Pa vapor cp 113.73 dH/dT 113.73 |
| gibbs_duhem | ok | 3.5e-08 | ['C1', 'nC4']@300K/500000Pa vapor 4.1e-09; ['C3', 'nC6']@300K/5e+06Pa hc_liquid 3.5e-08 |
| single_liquid_limit | ok | 0 | 300K/5e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 300K/3e+06Pa |

Note: L1/L2 cases bound 2026-11-04 (val-saft, data/validation/saft/cases-val.yaml) once data/validation/ was opened. The row is also checked by tests/thermo/test_soft_saft.py against the source's own published soft-SAFT numbers (Pamies 2003 Tables 4.4 and 4.5: critical temperatures and densities of n-C12..n-C48) and against CoolProp saturation, with the measured deviations recorded there: the PV parameters overpredict the vapour pressure of methane, ethane and propane by 5-24 % (Tr 0.6-0.9; liquid density within 1 %), n-butane to n-octane are within 5 % (Psat) and 2.5 % (rho_L), CO2 within 3 % (240-280 K), H2 within 5 % (20-30 K); n-C10 (correlation-derived, not fitted) runs 10-20 % low. Critical pressures of Table 4.4 are not reproduced (1-4 % high with the thesis's rounded PVrP correlation; temperatures match to 0.1 K). The bridge PT flash has no stability test: an asymmetric feed whose only density root is liquid-like (e.g. 20 % H2 in n-C10 at 400 K, 5 MPa) is returned as one liquid, not split.

### L4 cross-model pairs

- n/a — refuses the slice feed: SaftParameterError: no verified soft_saft parameters for ['C6+', 'H2O', 'N2', 'iC4', 'iC5']; supported: ['C1', 'C2', 'C3', 'CO2', 'H2', 'nC10', 'nC16', 'nC4', 'nC5', 'nC6', 'nC7', 'nC8'] (unsupported components are refused, never treated as ideal)

## L1/L2 reference-case outcomes

32/45 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `cpv-C1-125.0K` — coolprop:CH4
- `cpv-C1-155.0K` — coolprop:CH4
- `cpv-CO2-240.0K` — coolprop:CO2
- `cpv-CO2-265.0K` — coolprop:CO2
- `cpv-nC4-300.0K` — coolprop:n-Butane
- `cpv-nC6-350.0K-ss` — coolprop:n-Hexane
- `cpv-nC10-400.0K` — coolprop:n-Decane
- `ss-c1c3-277.59K-1.724MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 270, 277.59 K isotherm; retrieved 2026-10-20
- `ss-c1c3-294.26K-6.895MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20
- `ss-c1c3-310.93K-2.068MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 310.93 K isotherm; retrieved 2026-10-20
- `ss-c1co2-293.130K-6.135MPa` — Petropoulou, Voutsas, Westman, Austegard, Lovseth & Stang (2018) Fluid Phase Equilib. 462, 44-58, via NIST ThermoML, doi 10.1016/j.fluid.2018.01.011, 293.13 K isotherm; retrieved 2026-10-21
- `ss-c1co2-303.145K-7.306MPa` — Petropoulou, Voutsas, Westman, Austegard, Lovseth & Stang (2018) Fluid Phase Equilib. 462, 44-58, via NIST ThermoML, doi 10.1016/j.fluid.2018.01.011, 303.14 K isotherm; retrieved 2026-10-21

## References

- Blas & Vega, "Thermodynamic behaviour of homonuclear and heteronuclear Lennard-Jones chains with association sites from simulation and theory", Mol. Phys. 92 (1997) 135; Blas & Vega, "Prediction of binary and ternary diagrams using the statistical associating fluid theory (SAFT) equation of state", Ind. Eng. Chem. Res. 37 (1998) 660 (citations as listed in the Pamies thesis, refs 19 and 101)
- J. C. Pamies, PhD thesis, Universitat Rovira i Virgili (2003), https://repositori.urv.cat/repositori/getDocument/TDX%3A304?ds=Memoria&mime=application/pdf
- Johnson, Zollweg & Gubbins, "The Lennard-Jones equation of state revisited", Mol. Phys. 78 (1993) 591-618, doi:10.1080/00268979300100411
- Johnson, Muller & Gubbins, "Equation of state for Lennard-Jones chains", J. Phys. Chem. 98 (1994) 6413
- teqp 0.23 (Bell et al.), https://github.com/usnistgov/teqp, MIT licence
