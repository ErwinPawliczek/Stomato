# T3 pack notes — SR-POLAR open parameters + worked example (retrieved 2026-11-04)

## What this pack is

Board task T3: "SR-POLAR: find open published RKUPP p1-p3 parameters + c_i(T) translation
and a worked example". Reading note: "RKUPP" appears nowhere in the repo (grep 2026-11-04)
or in Crossref; the board row's title says SR-POLAR, so p1-p3 is read as the three
Schwartzentruber-Renon polar parameters (p0, p1, p2 in Mangold's notation). If the board
author meant a different four-parameter form, this pack still delivers the c_i(T) form and
the worked example; the p-set reading is flagged here.

Delivered: every openly retrievable SR-POLAR-family parameter set (H2O, O2, N2, CO2), the
temperature-dependent volume translation c(T) and alpha(T) with their published derivatives,
and the paper's worked ternary example (9 water-air points) as harness-ready cases.

## Source

Mangold, F.; Pilz, St.; Bjelic, S.; Vogel, F. "Equation of state and thermodynamic properties
for mixtures of H2O, O2, N2, and CO2 from ambient up to 1000 K and 280 MPa",
J. Supercritical Fluids 153 (2019) 104476. doi:10.1016/j.supflu.2019.02.016.
Open access (CC BY 4.0) on PubMed Central (PMC6919335); the supplementary-information PDF was
retrieved from the Elsevier CDN
(https://ars.els-cdn.com/content/image/1-s2.0-S0896844618307903-mmc1.pdf, 49 pp) after PMC's
own download endpoint answered a bot-gated proof-of-work page. All retrieved 2026-11-04.

Their model ("VTBMSR-III") is RKS + Schwartzentruber-Renon polar alpha + temperature-dependent
volume translation + non-quadratic Schwartzentruber-Renon mixing rules (a_mix with
(1 - k_a_ij - (xi-xj)l_ij), b_mix with (1 - k_b_ij)) — the SR-POLAR structure.

## Model equations as published (transcribed from the retrieved text)

- EOS (eq 14): p = RT/((v+c)-b) - a_c*alpha/((v+c)(v+c+b)), RKS constants
  a_c = (1/9)(2^(1/3)-1) R^2 Tc^2 / pc, b = (1/3)(2^(1/3)-1) R Tc / pc (eqs 15-16).
- Volume translation (eq 17): c = c0 + c1/(1 + c2 - Tr) for Tr <= 1 (the main text renders
  eq 17 ambiguously as "c0 + c1 1 + c2 - Tr"; the SI's derivative c' = c1/((1 + c2 - T/Tc)^2 Tc)
  (eq S1.45) fixes the reading as the reciprocal). For Tr > 1: c = c0 (c1 = 0 case, eq 19);
  the general Tr>1 branch is eq S1.44. Derivatives: S1.45-S1.48.
- alpha (eq 22a / SI S1.38): alpha = [1 + m(1-sqrt(Tr)) - p0 (1-Tr)(1 + p1 Tr + p2 Tr^2)]^2
  for Tr <= 1; alpha = [exp(cd(1-Tr^d))]^2 for Tr > 1 with d = 1 + 0.5 m - p0/(1+p1+p2)
  (eq 22d) and cd = 1 - 1/d (eq 22c). m = 0.48508 + 1.55191 omega - 0.15613 omega^2 (eq 22e).
  Derivatives alpha', alpha'': SI eqs S1.39-S1.42.
- Binary interaction (eq 26): k_b_ij = kb0 + kb1*T + kb2/T (same form for k_a_ij, eq 25;
  k_a and l are not used in the paper: "k_a_ij(z) and l_ij(z) are not used").

## Worked example (the pack's cases)

Table 8 of the main article: ternary water-air molar volume, experimental values from
Japas & Franck [30], air composition assumed x_O2/x_N2 = 1/4 by Mangold (Japas & Franck do
not specify it — flagged in every case). Nine single-phase supercritical points,
x_H2O 0.791-0.798, T 620.5-657 K, P 27.0-263.9 MPa. The paper reports the VdW reference error
(4.1 to 57.8 %) and the VTBMSR-III error (0.4 to -15.0 %) per point; data.csv carries both
columns. Below 35 MPa the paper states the VTBMSR-III error is < 1 %.

Worked numbers (computed for this pack from the printed parameters, arithmetics only):
water vapour/supercritical set (p0 = -1.92140347, p1 = -1.1392853, p2 = 0.22028766),
omega = 0.344 -> m = 1.000461. At T = 620.5 K (Tr = 0.958834):
alpha = 1.059912; c = c0 + c1/(1 + c2 - Tr) = 1.204378e-05 m3/mol.
The first case (620.5 K, 27.0 MPa) is the natural L3 anchor: the paper's own model error
there is 0.4 %, so a correct implementation should sit near that against the experimental
density.

## Coverage and gaps (NOT FOUND / paywalled)

- Methanol, ethanol, acetone, ammonia three-parameter p-sets in the Schwartzentruber-Renon
  form: NOT FOUND openly. Looked at (2026-11-04): Schwartzentruber & Renon, I&ECR 28 (1989)
  1049 (paywalled, no OA copy anywhere); Jordison, Lira & Miller, I&ECR 54 (2015)
  doi:10.1021/acs.iecr.5b02409 (paywalled; its SI is not on the ACS CDN); the author's
  open thesis (Jordison 2016, Michigan State, d.lib.msu.edu/etd/3937) returns 403 to all
  scripted access (PDF/TXT datastreams and mirrors docslib/studyres are bot-gated);
  pychemqt implements Mathias-1983 (single polar parameter) but no Schwartzentruber class;
  NeqSim implements the alpha form without a cited parameter table. This matches and
  confirms the catalogue's 2026-11-03 note in docs/thermo-catalogue-plan.md.
- Mangold's numbers carry the structural caveats the catalogue already recorded: regressed
  to density/caloric data (not vapour pressure), water split into separate liquid and
  vapour/supercritical p-sets (a VLE flash needs a decision on which alpha runs where;
  the paper's own rule is Tr <= 1 vs Tr > 1 per eq 22), no vapour-pressure validation
  printed. The pack pins the data; closing the catalogue row stays a separate decision.
- The original Schwartzentruber & Renon alpha form ((1-Tr) vs (1-Tr^0.5) in the polar term)
  remains unverifiable from open sources; Mangold's own printed form (both main text and
  SI) is the (1-Tr) version, and these p values are bound to it.

## Transcription quality

Main-article Table 5 and SI Tables S1.1/S1.2 were both retrieved and cross-checked: they
agree on every shared value except one rounding-level difference (c2 for water: 0.4054292
in Table 5 vs 0.405429 in SI S1.1). The SI additionally carries the alternate parameter
sets (H2O liquid set 1, O2 sets x2-x5, N2 set 2, CO2 set 1) that the main article lists by
number only; params.csv marks the source table of every row. Binary kb values: Table 7
(main) and SI S1.3-S1.6 agree exactly on the four regressed pairs; CO2/O2 and O2/N2 are
zero by the paper's choice.
