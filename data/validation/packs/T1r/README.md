# T1r — ethanol/water isobaric VLE (NRTL) data pack

Task T1r (agents/BOARD.md, branch `agents-board`), executed by Obvious on 2026-11-04.

Deliverables: `data.csv` (17 rows) and `pack.yaml` (15 cases, `package: nrtl`).
Units: T [K], P [Pa abs], mole fractions (per repo convention).

## Pack (b): ethanol(1) + water(2), isobaric 101.3 kPa — DELIVERED

Single source, transcribed 1:1 from the open NIST ThermoML XML, retrieved 2026-11-04:

- **Lai, H.-S.; Lin, Y.-F.; Tu, C.-H.** "Isobaric (vapor + liquid) equilibria for the
  ternary system of (ethanol + water + 1,3-propanediol) and three constituent binary
  systems at P = 101.3 kPa." *J. Chem. Thermodyn.* **68** (2014) 13–19.
  DOI [10.1016/j.jct.2013.08.020](https://doi.org/10.1016/j.jct.2013.08.020)
- Open machine-readable record: <https://trc.nist.gov/ThermoML/10.1016/j.jct.2013.08.020.xml>

What was taken from it (ThermoML `PureOrMixtureData` dataset numbers, verified by direct
parsing of the XML):

| dataset | content | points |
|---|---|---|
| 9 | boiling temperature vs liquid mole fraction at 101.3 kPa | 16 |
| 10 | vapour mole fraction vs liquid mole fraction at 101.3 kPa | 16 |
| 11 | azeotropic temperature at 101.3 kPa | 1 (351.32 K) |
| 12 | azeotropic composition at 101.3 kPa | 1 (x_EtOH = 0.891) |

Ethanol-basis check: dataset 9 anchors at x_EtOH = 1 → 351.45 K (ethanol normal b.p.)
and x_EtOH = 0 → 373.15 K (water normal b.p.) confirm the mole-fraction basis is
ethanol(1) + water(2) as transcribed; the azeotrope composition 0.891 matches the
well-known ethanol/water azeotrope region. No value was converted, tuned or interpolated.

Pressure handling: the source prints **101.3 kPa** (both in the title and as the ThermoML
constraint). The pack records it as 101300 Pa and does not silently upgrade it to
101325 Pa. If the binding harness requires exactly 101325 Pa, that is a decision for the
Stomato bot, not a data edit.

## Pack (a): ethane(1) + propane(2) binary VLE for Peng-Robinson — NOT FOUND

No openly retrievable, tabulated experimental binary VLE data (bubble P, x, y vs T) for
the ethane + propane system was found. What was checked on 2026-11-04, in order:

| where | what | result |
|---|---|---|
| NIST ThermoML archive (trc.nist.gov/ThermoML) | searched for ethane/propane mixture records; downloaded and parsed 9 candidate DOIs (10.1021/je500130j, 10.1021/je4000857, 10.1016/j.fluid.2010.12.012, 10.1016/j.fluid.2005.12.004, 10.1021/je700210n, 10.1021/je300806e, 10.1016/j.fluid.2006.02.016, 10.1007/s10765-013-1539-3, 10.1021/je020127z) | no ethane+propane binary VLE dataset in any of them (nearest: ethane+hexafluoroethane, ethane+nitrogen, propane+tetrafluoromethane, propane+R134a/R143a, ethane/squalane, propane/squalane) |
| DDB Explorer Edition (ddbst.com) | "Propane + Ethane" listed in the free Explorer 30-compound set (HPV databank) | system exists but values are not exposed; the Online DDB "Details" page (ddbonline.ddbst.com/DDBSearch/onlineddboverview.exe?submit=Details&systemcomplist=237%2C1054) offers a paid quote only — **paywalled** |
| Miksovsky & Wichterle, Collect. Czech. Chem. Commun. 40 (1975) 365, DOI 10.1135/cccc19750365 | the main open-archival candidate (CCCC digital archive) | page exists at cccc.uochb.cas.cz/40/2/0365/ but full text is **"Buy full text"** only; no open PDF on the live site or in the Wayback Machine snapshots of the /pdf/ path |
| classic JCED/IEC papers (Matschke & Thodos 1962 DOI 10.1021/je60013a022; Djordjevich & Budenholzer 1970 DOI 10.1021/je60044a020; Wichterle/Kobayashi-era JCED 1979 DOI 10.1021/je00052a015; Reamer/Sage/Lacey ethane-propane work) | all indexed, none open | **ACS-paywalled** throughout; no author manuscripts or repository copies found |
| IUPAC-NIST Solubility Data Series, vol. 27/28 (srdata.nist.gov/solubility/IUPAC/SDS-27-28/, pages fetched: 1, 50, 248, 266, 281, 297, 303, 314, 320, 338) | page 266 evaluates the methane+propane binary (gases-in-liquids scope) | this volume series covers **gas solubility**, not binary alkane VLE; the C2/C3 binary as a VLE system is out of its scope |
| NISTIR 3953 "Tables of experimental data used for the correlation of the thermophysical properties of ethane" (govinfo.gov, 312 pp.) | full-text scanned | pure ethane only — zero propane mentions |
| NBS Technical Note 4 (Ziegler 1959, nvlp ubs.nist.gov) | vapor pressures of 11 hydrocarbons | pure-component vapor pressures only, no mixtures |
| DECHEMA CDS sample PDF (dechema.de, CDS01Pt01.pdf) | free sample of the VLE Data Collection | sample systems do not include ethane+propane; full series is **paywalled** |
| OSTI "Thermodynamics of the liquid mixture ethane + propane below 270 K. Topical report, January 1990" (osti.gov/scitech/biblio/5933291) | the only government report found dedicated to this binary | full text URL https://www.osti.gov/servlets/purl/5933291 returns **404 "Page Not Found"** |
| university repositories (CaltechTHESIS, Rice scholarship, TTU-IR, K-State K-REX, BYU, KU, UKentucky uknowledge, core.ac.uk) | searched for thesis scans with C2/C3 tables | near misses only: Caltech McKay 1959 (ethane-propene, not propane), Rice Price-Kobayashi ternary C1-C2-C3 (metastable link, and ternary not binary) — no open binary C2/C3 table surfaced |

The classic ethane/propane datasets exist in the literature (Kay 1927-onwards, Sage et
al., Matschke & Thodos, Djordjevich & Budenholzer, Miksovsky & Wichterle, and the
reviewed/recommended Wichterle & Kobayashi 130–214 K and Price & Kobayashi 144–278 K
sets cited in SDS 27/28 p. 266) but every open retrieval route to their numeric tables
ended in a paywall or a dead link as documented above. Per the data rules, no values are
transcribed and no pack (a) cases are written.

## Structure / conventions

- `pack.yaml` (not `cases*.yaml`) so the harness does not auto-run it; binding is the
  Stomato bot's call.
- `package: nrtl` (the registered NRTL package) — cases run when bound.
- `EtOH` is used as the component id, mirroring the existing gamma-phi case
  `nrtl-ig-etohh2o-azeotrope-101.325kPa`. Note for the bot: `EtOH` is **not** in the
  curated `data/components.yaml` slate (locked file); cases will not resolve until EtOH
  is curated (CAS 64-17-5).
- Tolerances: bubble_T 0.5 % relative, vapour composition 0.02 absolute (P1-05
  conventions, docs/validation.md).
- No V1 files (`data/validation/*/cases*.yaml`) touched.

## Tests run

None — data-only change (two CSV/YAML/MD files under `data/validation/packs/T1r/`). No
Python source was modified; the repo test suite is unaffected. pack.yaml was validated
structurally (YAML parses; case fields match the cases.yaml schema: id, package,
components, z, P, source, expected{bubble_T, vapor_comp}, tolerance) — `uv run` was not
used because the sandbox does not have the project venv provisioned for this branch and
no dependency change or code change was made.
