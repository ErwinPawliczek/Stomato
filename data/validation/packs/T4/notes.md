# T4 — API liquid density for petroleum pseudo-components

Task: find public reproductions of API Technical Data Book Procedure 6A3.5 (liquid density of
petroleum fractions, modified Rackett / Spencer–Danner with API constants) with worked examples
(inputs Tb/SG/MW or API gravity; output liquid density). All values below were read from
documents retrieved on 2026-11-04 and re-derived numerically before transcription. No values are
estimated, tuned, or recalled from memory. Units in the pack are K, Pa, kg/m3 per PROTOCOL.md;
source-native units are kept in the notes and converted only where the conversion is exact
(lb/ft3 → kg/m3, °R → K, psia → Pa).

## 1. Primary source: API TDB density chapter, public e-ballot draft

- **Document:** "Technical Data Book: Part 6 – Density", API Technical Report TDB-6, 1st
  Edition draft (ballot draft, undated internal draft; chapter content carries per-procedure
  edition years). Publicly accessible URL (no paywall, no login):
  `https://eballotprodstorage.blob.core.windows.net/eballotscontainer/TDB-6_e1%20draft.pdf`
  (retrieved 2026-11-04). Each page is marked "This document is not an API Standard; it is under
  consideration within an API technical committee…" — it is a committee ballot draft, not a
  published standard. Treat the numbers as the procedure as balloted; the final published TDB
  (paywalled) is the authority of record.
- **What the draft contains:** the complete density chapter. The petroleum-fraction low-pressure
  liquid-density procedure — historically numbered **6A3.5** in TDB editions that used the 6A3
  numbering — appears as **Procedure 6A2.3, "Density of Liquid Petroleum Fractions at Low
  Pressures with the Modified Rackett Equation (1992)"** in this draft's renumbered layout
  (draft PDF pages 34–36; internal page numbers 6-34 to 6-36). Comments section dated (2010),
  Reliability: "average error of 0.75 percent when tested against a data set consisting of
  several high-molecular-weight hydrocarbons and petroleum fractions". Literature source cited
  by the draft: "Private communication, Spencer, C. F., M. W. Kellogg Co., Houston, Texas
  (1983)."
- **Note on numbering:** the draft's own TOC has no 6A3.x section; the task's "6A3.5" refers to
  the same procedure in older TDB layouts (independent confirmation that the 1992 modified
  Rackett petroleum-fraction procedure is the API-recommended method: the IJERT paper cited in
  §3 cites "procedure 6A3.5 of API (1997)" for hydrocarbon liquid density). The draft does not
  print the old number; the identity is established by content (modified Rackett, MeABP + SG
  inputs, ZRA back-calculated from a known density).

## 2. Procedure 6A2.3 (= historical 6A3.5): equations and constants, as printed in the draft

**Equation (6A2.3-1):**

```
rho = (Ppc * M / (R * Tpc)) * ZRA^(1 + (1 - Tr)^(2/7))
```

with (draft's variable list, verbatim meaning):

- `rho` = density of liquid petroleum fraction, lb-mol/ft3
- `R` = gas constant = **10.732 (psia)(ft3)/(lb-mol)(°R)** (a printed constant of the procedure)
- `Tr` = reduced temperature, `T / Tpc`
- `T` = temperature, °R
- `Tpc` = pseudocritical temperature, °R (from Chapter 4 procedures)
- `Ppc` = pseudocritical pressure, psia (from Chapter 4 procedures)
- `ZRA` = "an empirically derived constant" (the Spencer–Danner modified-Rackett
  compressibility factor); per Step 3 of the procedure, ZRA is **back-calculated from Eq.
  (6A2.3-1) using the specific gravity or density at a known temperature** (in practice the
  60°F density from SG). This is the defining API usage: ZRA is not looked up from a table for
  fractions; it is fitted so the correlation reproduces the fraction's known reference density.

**Procedure steps as printed:** (1) from assay data get MeABP and SG at 60°F (Chapter 2
procedures); (2) get Tpc, Ppc, and molecular mass from Chapter 2/4 procedures; (3) back-calculate
ZRA from Eq. (6A2.3-1) at the known density point; (4) apply Eq. (6A2.3-1) at other temperatures.
Alternative: read density off Figure 6A2.4, the Ritter–Lenoir–Schweppe nomograph, given any two
of Watson K, MeABP, API gravity.

The correlation form is the Spencer–Danner (1972) modified Rackett equation; the draft cites the
1983 Spencer private communication as its source.

## 3. Worked example printed in the draft (PDF pages 35–36) — fully re-derived

**Inputs:** petroleum blend, MeABP = 538 °F, API gravity = 30.6; find liquid density at 160 °F
and atmospheric pressure. Printed reference result: experimental 0.8343 g/mL (draft ref 7a).

Printed steps, each re-derived in Python before transcription (deviations noted where my
unrounded value differs from a printed rounded intermediate):

| quantity | printed | re-derived (this session) | note |
|---|---|---|---|
| MeABP | 997.7 °R (= 538 + 459.7) | 997.7 | |
| SG = 141.5/(API+131.5) | 0.87292 | 0.8729180 | |
| rho(60°F) = SG × 0.999016 | 0.87206 g/mL | 0.8720590 | 0.999016 g/mL = water at 60°F, 1 atm (draft §6-0, and eq. 1a citation) |
| rho(60°F) | 54.441 lb/ft3 | 54.4409 | × 62.428 |
| M (Ch. 2 correlation, see below) | 215.1 | 215.127 | |
| Tpc (Ch. 4 correlation) | 1355.6 °R | 1355.666 | |
| Ppc (Ch. 4 correlation) | 273.2 psia | 273.145 | |
| Tr at 60°F | 0.3834 | 0.38335 | |
| ZRA (back-calculated) | 0.2490 | 0.249009 | |
| Tr at 160°F | 0.4571 | 0.457118 | |
| V(liq) at 160°F | 4.125 ft3/lb-mol | 4.126369 | |
| V | 257.5 cm3/g-mol | 257.601 | × 62.428 |
| rho(160°F) | 0.8353 g/mL | 0.835117 | |
| experimental | 0.8343 g/mL | — | printed; not re-derivable |

The small (≤0.03 %) differences vs printed intermediates come from the draft's own rounding of
trailing digits inside the printed chain; the final rho agrees to 0.0002 g/mL (0.024 %) and the
printed example itself closes to 0.12 % against the experimental value.

**The Chapter 2 / Chapter 4 correlations as printed in the example** (these print the constants
the procedure uses; they are the API/Riazi–Daubert-style forms):

- M = 20.486 · exp[1.165×10⁻⁴·Tb − 7.78712·SG + 1.1582×10⁻³·Tb·SG] · Tb^1.26007 · SG^4.98308
  (Tb in °R) → printed M = 215.1
- Tpc = 10.6443 · exp[−5.1747×10⁻⁴·Tb − 0.54444·SG + 3.5995×10⁻⁴·Tb·SG] · Tb^0.81067 ·
  SG^0.53691 (Tb in °R) → printed Tpc = 1355.6 °R
- Ppc = 6.162×10⁶ · exp[−4.725×10⁻³·Tb − 4.8014·SG + 3.1939×10⁻³·Tb·SG] · Tb^(−0.4844) ·
  SG^4.0846 (Tb in °R) → printed Ppc = 273.2 psia

(The draft's typesetting of the Ppc exponent of SG renders as "4.0846"; re-derivation with that
value reproduces the printed 273.2 psia, confirming the reading. The exponent "−0.4844" on Tb is
similarly confirmed by re-derivation.)

**Density-unit conversion used by the procedure:** rho[lb/ft3] = rho[g/mL] × 62.428; water at
60°F/1 atm = 0.999016 g/mL (draft §6-0).

## 4. Corroborating reproduction: Spencer–Danner modified Rackett as applied to pseudo-components

**Document:** J. I. Ramos-Pallares, PhD Thesis, University of Calgary, 2017, "An experimental
and modeling study of the phase behaviour of bitumen + solvent mixtures" (title as indexed;
file: `2017 PhD Thesis Francisco Ramos Pallares.pdf`).
URL: `https://ucalgary.ca/ENCH/AER/theses/2017%20PhD%20Thesis%20Francisco%20Ramos%20Pallares.pdf`
(also mirrored at `https://www.ucalgary.ca/eng/ENCH/AER/theses/2017%20PhD%20Thesis%20Francisco%20Ramos%20Pallares.pdf`),
retrieved 2026-11-04. Open access (thesis repository).

- **Equation 6.8** (thesis p. 133, PDF p. 160): `vs = (R·Tc/Pc) · ZRA^(1 + (1 − T/Tc)^(2/7))`,
  credited to Spencer and Danner (1972); vs = saturated-liquid molar volume; density = M/vs;
  pseudo-component density at atmospheric pressure taken equal to the saturated-liquid density
  (compression correction negligible, citing Motahhari et al., 2013).
- **ZRA determination (thesis p. 133 and p. 178):** "The Rackett compressibility factor was
  determined by tuning Equation 6.8 applied at 15.6°C to fit the previously determined specific
  gravity" — the same SG-anchored usage as API 6A2.3/6A3.5.
- **Parameter tables (thesis pp. 332–334, PDF pp. 359–361), Tables E.1–E.6:** per
  pseudo-component (12 cuts per oil): weight fraction, Tb (K), SG, Tc (K), Pc (kPa), ZRA, H/C,
  density at 37.7 °C (kg/m3), viscosity, and EF-model constants. Example row (Table E.3,
  US-HO-A1, cut 6): Tb = 574.9 K, SG = 0.918, Tc = 773.6 K, Pc = 2091.5 kPa, ZRA = 0.3800,
  rho(37.7 °C) = 917.9 kg/m3.
- **Reproduction check performed this session:** using each table's own Tb-independent inputs
  (Tc, Pc, ZRA, SG) and the thesis's stated tuning rule (ZRA such that rho at 288.75 K equals
  SG × 0.999016 g/mL), the Rackett molar volume at 288.75 K fixes M, and rho at 310.85 K then
  follows. For five rows checked (E.3 cuts 1, 6, 9; E.1 cut 1; E.2 cut 3) this reproduces the
  printed rho(37.7 °C) to −1.1 % to −2.3 %. The residual is consistent with the thesis applying
  its own additional tuning (the thesis tunes SG values of cuts to match the measured whole-oil
  SG before computing ZRA, and may use different M than back-derived); therefore these tables
  are recorded as **parameter data (Tb/SG/Tc/Pc/ZRA)**, NOT as validation cases. A pack case
  built on them would encode our reconstruction, not a printed input→output pair.

## 5. Independent citation of the procedure number

**Document:** "Shortcut Modeling of an Existing Atmospheric Crude Distillation Column",
IJERT V13, issue 07, paper 052 (2024).
URL: `https://www.ijert.org/research/shortcut-modeling-of-an-existing-atmospheric-crude-distillation-column-IJERTV13IS070052.pdf`,
retrieved 2026-11-04. Open access. Quote (p. 2 of 9): "The viscosity and density of hydrocarbon
components were determined from procedures 11A4.1 and **6A3.5** of API (1997) respectively."
Used only to confirm that the historical procedure number for petroleum-fraction liquid density
is 6A3.5 (API TDB 1997 edition numbering); it contains no equations or data from 6A3.5.

## 6. Sources looked at and rejected / NOT FOUND items

- **Riazi, *Characterization and Properties of Petroleum Fractions*, ASTM MNL50 (2005):** the
  author's public sample PDF (`http://www.riazim.com/sample/MNL50.pdf`, retrieved 2026-11-04)
  contains front matter and tables of contents only — §5.8 "Generalized Correlation for PVT
  Properties of Liquids—Rackett Equation" (pp. 222–224) exists but its body text and any worked
  example are **not** in the sample. Full text paywalled (ASTM store:
  `https://store.astm.org/mnl50-eb.html`). → NOT FOUND (paywalled: MNL50 §5.8 and Chapter 7
  density sections with worked examples). A Scribd scan copy exists but was not used
  (accessibility/legibility and licence concerns).
- **Original Rackett (1970) paper:** "Equation of state for saturated liquids", C. F. Rackett,
  J. Chem. Eng. Data 15(4) (1970). Paywalled (ACS). Not needed: the API procedure as printed in
  the ballot draft is the primary artifact, and it cites the 1983 Spencer private communication.
- **Valderrama & Abu-Sharkh (1989), FPE 51:87–100,** "Generalized Rackett-type correlations to
  predict the density of saturated liquids and petroleum fractions" (DOI
  10.1016/0378-3812(89)80010-9 as indexed): only a Scribd scan of uncertain provenance was
  reachable; tables could not be reliably transcribed from search snippets alone, and per task
  rules no value was taken from a snippet. → NOT USED.
- **API TDB published editions (1997, 2016):** paywalled. → NOT FOUND (paywalled; the 202X
  ballot draft of Part 6 above is the open artifact).
- **Nji, "Characterization of Heavy Oils and Bitumens" (Calgary thesis,
  collectionscanada.gc.ca NR62165.PDF):** download returned an HTML error page, not a PDF.
  → NOT FOUND (broken link: `https://collectionscanada.gc.ca/obj/thesescanada/vol2/002/NR62165.PDF`,
  HTTP response was HTML).
- No publicly available, line-by-line reproduction of the **published** (non-draft) API 6A3.5
  with its own worked example was found; the ballot draft of the renumbered procedure with its
  full example is the closest open artifact and is what the pack encodes.

## 7. What went into the pack

`data.csv` + `pack.yaml` (same directory) encode the draft's worked example as two
validation cases, converted exactly to K / Pa / kg/m3:

1. **t4-api-6a2-3-zra** — the ZRA back-calculation step: inputs MeABP, API gravity, T = 60 °F;
   expected ZRA = 0.2490 (printed; re-derived 0.249009).
2. **t4-api-6a2-3-rho160** — the density prediction at 160 °F: same fraction, expected
   rho = 0.8353 g/mL = **835.3 kg/m3** (printed; re-derived 835.12; experimental 834.3 kg/m3,
   0.12 % below the calculated value).

Supporting constants transcribed into `pack.yaml` case metadata (M, Tpc, Ppc in SI, with °R/psia
natives in notes.md) come from the same printed example. Both cases carry the source string
with the draft URL and pages.
