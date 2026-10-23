# T-19 research record — retrieved sources and numbers

Every number below was retrieved this session (2026-10-23) with the source URL noted.
This file is the working citation trail for the spec steps; final citations land in
the params/case provenance.

## ideal_solid (step 1)

Van't Hoff ideal solubility, x = exp(-(dHfus/R)(1/T - 1/Tm)), gamma = 1.
The model is solvent-independent; the measured points are per (solute, solvent).

- Naphthalene in benzene, 298.15 K: x = 0.292 (Chang 1969, Ph.D. Dissertation,
  North Dakota State Univ.; interpolated at 298 K, compiler error +-2%).
  IUPAC-NIST Solubility Database sysID 59_123,
  https://srdata.nist.gov/solubility/sol_detail.aspx?sysID=59_123
- Naphthalene in benzene, 307.5 K: x = 0.372 (Ward, J. Phys. Chem. 30, 1316
  (1926)); 308.2 K: x = 0.3766 (McLaughlin & Zainal, J. Chem. Soc. 1959, 863).
  sysID 59_125 and 59_124. Consistency: Kravchenko, Zhur. Fiz. Khim. 13, 133
  (1939) gives 0.380 at 307.4 K (sysID 59_126).
  NOTE: on these IUPAC pages the x1/x2 column headers follow the component list
  (1)=benzene, but the liquidus values only make sense with x1 = the SOLUTE
  (naphthalene): e.g. Ward at 343.5 K has x1 = 0.833, which must approach
  naphthalene's melt (353.35 K), and Kravchenko's benzene-freezing branch at
  276.5 K has x1 = 0.031, which matches ideal-freezing-point depression of
  benzene by 3.1 mol% naphthalene. Cite the solute mole fraction, not x1.
- Biphenyl in benzene, 298 K: x = 0.381 (Chang 1969), regression
  ln x1 = -2233.1/T + 6.5272 (r = 0.9998) gives 0.3819.
  IUPAC-NIST sysID 58_241 (evaluated by W.E. Acree Jr., June 1994),
  https://srdata.nist.gov/solubility/sol_detail.aspx?sysID=58_241
- Anthracene in benzene, 298.15 K: TO CONFIRM against a primary page
  (secondary aggregations quote ~0.0074 mole fraction; the same aggregations
  mislabel mol/L as mole fraction, so the primary table is required).

## hoc_dimer (step 4)

- Ritter & Simons, J. Am. Chem. Soc. 67, 757 (1945): log10 K2 = 3164/T - 10.4184
  with K2 in mmHg^-1 (monomer-dimer chemical theory; their full model also has a
  tetramer term, K4 in mmHg^-3). Slope conversion: dH_assoc = -3164 R ln(10) =
  -60.6 kJ/mol — the shipped -25 kJ/mol disagrees with the Ritter-Simons slope.
  Converted to a Pa basis: K2_Pa = K2_mmHg / 133.322.
- At T_ref = 399.35 K this gives K2 = 2.41e-5 1/Pa and a PREDICTED nominal
  Z = 0.683 at 1 bar, vs the Mehling & Kleiber (2020) measured Z = 0.6299 — an
  independent miss of ~8%, assessable per T-15 discipline (parameter source !=
  reference source; the current shipped K2 was reduced FROM the Z point, which
  is exactly the round-trip the rules forbid binding).
- K2 conversion derivation (pressure-basis change of units): Kp[1/Pa] =
  p_D[Pa]/p_M[Pa]^2 = (p_D[mmHg]*133.322)/(p_M[mmHg]*133.322)^2
  = Kp[1/mmHg]/133.322.

## hf_hexamer (step 5)

Jarry & Davis 1953 parameters are already in association.yaml with the paper's
own smoothed association factors as test anchors. TODO: recheck a/Pa-basis
conversion line and the predicted vs smoothed factors; bind a case at a NEW
temperature from the paper's table if the table is retrievable open.

## polymer rows (steps 2-3)

- PS/toluene chi = 0.35 at 338.15 K is listed in the Chicago Polymer Database
  (pppdb.uchicago.edu/chi) with a Macromolecules citation - different T from the
  shipped Gunduz & Dincer 0.67 at 435.46 K; not directly bindable without the
  original table.
- Bawn et al. 1950 (PS/toluene osmometry) and Krigbaum & Geymer, JACS 81, 1859
  (1959) (PS/cyclohexane near theta) are the spec-named sources; both ACS
  paywalled. Search for open digitized tables ongoing; if none is open, the row
  stays experimental with the documented search (spec escape hatch).
- Chen 1993 polymer NRTL published parameter set: not yet located open; search
  documented in the row note if it stays experimental.
