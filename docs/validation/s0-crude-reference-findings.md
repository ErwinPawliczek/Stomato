# S0-D findings note: completing the S0 crude-unit reference

Task: complete `data/validation_units/refining/s0_reference.yaml` with printed,
citable numbers (spec `specs/backend/S0-D-crude-reference-completion.md`,
GitHub issue #236). Rules followed: only values printed in a table or text;
no chart digitised; no value back-solved; no simulator output used unless the
paper prints it as its published result; never two units mixed into one
reference.

## What was searched

All papers are author-hosted PDFs on the University of Oklahoma site of the
author series (`ou.edu/class/che-design/pub-papers/`); each was downloaded
and read in full (text layer extracted, and every number transcribed into the
reference verified against a rendered image of the printed page):

| Paper | What it holds for the S0 unit |
|---|---|
| Bagajewicz & Ji, I&EC Res. 40 (2001) 617-626, Part I: Targeting | Feedstocks (Table 1), TBP and light ends (Tables 2-3), product specs and withdrawal trays (Table 4), Watkins tray guidelines (Table 5), printed simulation results for the no-, one-, two- and three-pumparound schemes (Tables 6, 7, 8, 9), diesel steam flow rates (text, p. 624) |
| Bagajewicz & Soto, I&EC Res. 40 (2001) 627-634, Part II: HEN | Stream data for the same unit (CP, in/out temperatures for every product, pumparound, condenser and crude stream — Table 1), minimum utilities and pinch (Table 3), desalter temperatures (text) |
| Bagajewicz & Soto, I&EC Res. 42 (2003) 1196-1203, Part III: trade-off between complexity and energy savings | HEN-complexity trade-off only; no additional column data (no stage counts, yields, or pressures beyond Parts I/II) |
| Ji & Bagajewicz, I&EC Res. 41 (2002) 6095-6100, "Design of Crude Distillation Plants with Vacuum Units. I. Targeting" | The same light crude (845 kg/m3, 36.0 API, 795 m3/h — Table A.1) with a vacuum column: vacuum tower specifications (Table 1), vacuum pumparound loads (Table 4), complete-plant yields, gaps and steam supplies (Table 5) |
| Ji & Bagajewicz, I&EC Res. 41 (2002) 6100-6106, "…with Vacuum Units. II. HEN" | HEN design on Part I's targets; no additional column data |
| Ji & Bagajewicz, "On the Energy Efficiency of Stripping-Type Crude Distillation", I&EC Res. 41 (2002) | A different (stripping-type) configuration, used for the energy comparison; no conventional-column data beyond Parts I/II |

Also considered and **not** used: Watkins, *Petroleum Refinery
Distillation* (1979) — the pages needed are not openly available, and the
reference no longer needs it: the design series prints the same numbers
Watkins' guidelines produce (the papers cite Watkins for the tray
guidelines and the 10 lb/bbl steam basis). Inamdar, Gupta & Saraf (2004)
describes a **different unit** (different crude and feed rate), so it cannot
complete this reference under the same-unit rule.

## What was found (now recorded in `s0_reference.yaml`)

Everything the spec lists except one item (below), all from the same unit —
same crude, same 795 m3/h feed:

- **Product yields/rates** (m3/h, printed): one-PA 248/146/70/121/211; two-PA
  244/145.6/73.6/121.6/210.5; three-PA 244/145.5/72.5/123.85/209.7 (Part I
  Tables 6, 9); complete atmospheric+vacuum plant 244.39/144.76/71.82/124.25
  + LVGO 22.92, HVGO 81.43, vacuum overhead 0.202, vacuum residue 105.53
  (Vacuum-I Table 5).
- **Stage counts**: 34 trays main column, feed tray 29, draws at trays
  1/9/16/25, 4 trays per stripper (Part I Table 4 + text); vacuum tower 7
  trays (Vacuum-I Table 1).
- **Side strippers**: 3 (kerosene, diesel, gas oil), 4 trays each; the
  residue is steam-stripped at the column bottom, no separate vessel.
- **Pumparound count resolved**: the paper's base conventional scheme has
  **one** top pumparound (62.14 MW, Part I Table 6); its final light-crude
  design has **three** (22.3/33.7/8.8 MW, Part I Table 9, confirmed
  stream-for-stream by Part II Table 1). The plan's "two" is the printed
  intermediate scheme (Part I Table 9 left column). All three variants are
  recorded.
- **Pumparound duties and temperature ranges**: as above plus PA positions
  (PA1 draw tray 4 / return tray 2; PA2 between trays 10 and 12; PA3 between
  trays 17 and 19).
- **Stripping steam**: ratios (lb/h steam per bbl/h product) for all four
  stripped streams in every scheme (Part I Tables 6, 9); diesel steam in
  absolute units 32.5/48.5/113.4 kg mol/h for the 1/2/3-PA designs (Part I
  text, p. 624); Watkins' 10 lb/bbl design basis (text); vacuum bottom steam
  2.74 lb/bbl (Vacuum-I Table 1).
- **Flash zone**: temperatures 358.6-359.0 C (atmospheric, per scheme) and
  382 C at 1.90 psia (vacuum; = 13.1 kPa = 98.3 mmHg, inside the printed
  25-100 mmHg control band).
- **Heat data**: condenser duties, pumparound CP/temperature data, crude
  preheat trains, minimum utilities and pinch (Part II Tables 1, 3), complete
  plant steam supplies and energy consumption (Vacuum-I Table 5).

## What is still missing

- **Atmospheric flash-zone pressure and column-top pressure.** No paper of
  the series prints any atmospheric-column pressure. This is the single
  required item that could not be found in an open printed source.
- Tray efficiency (the paper counts trays); vacuum packing-section
  temperatures and vacuum column-top pressure.

## Recommendation

**Keep the reference.** It now carries a complete, internally consistent,
single-unit dataset (assay + configuration + rates + duties + steam) from
one design-paper series, which is what round 2 needs; replacing it with
another open unit (e.g. Inamdar/Gupta/Saraf 2004) would trade a same-unit
complete reference for a different, less-documented one. The atmospheric
flash-zone **pressure** should stay in `not_recorded`; if a pressure spec is
ever required for the S0 validation flowsheet, the honest options are a
typical-value note from an open textbook (clearly flagged as not from this
unit) or a new dedicated source search — not a back-solved number.
