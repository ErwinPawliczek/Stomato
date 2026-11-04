# T6 — polymer-solvent VLE pack (solvent activity / total pressure)

Open experimental data for solvent activity / total vapour pressure over binary
polymer solutions, **independent of Kiss et al. (2009) and of Lieu/Prausnitz/Gauthier
LBNL-43073**. Every value carries its citation in-file (author/year, DOI or URL,
table, page, retrieval date). Nothing was invented, estimated, interpolated, or
fitted; gaps are recorded as NOT FOUND.

## Files

- `data.csv` — one row per measured point (65 rows), `csv.QUOTE_ALL` + CRLF.
  Columns: system, solvent, polymer, polymer_Mw_g_mol, T_K, w_solvent, w_polymer,
  x_solvent, x_polymer, P_Pa, a_solvent, P1o_Pa, source, retrieved.
  Weight fractions are as published; mole fractions are computed from the published
  weight fractions using the polymer Mw stated by the source and solvent Mw from
  NIST WebBook (retrieval 2026-11-04). `a_solvent` is the source's own printed
  activity where the paper prints one, otherwise P/P1o from the same row's columns.
- `pack.yaml` — 59 validation cases in the `data/validation/<family>/cases.yaml`
  schema (binary points only; pure-solvent anchors stay in data.csv). Named
  `pack.yaml` so the harness does not run it until the Stomato bot binds it.

## Systems

| id | system | T (K) | polymer Mw (g/mol) | n (binary) | source |
|----|--------|-------|--------------------|------------|--------|
| S1 | toluene + polystyrene | 363.15 / 373.15 / 383.15 | 250,000 | 18 | Pavlicek/Bogdanic/Wichterle, CABEQ 29 (2015) 1-4, Table 2 p. 2, doi:10.15255/CABEQ.2015.2183 |
| S2 | chloroform + PS | 323.15 | 50,000 | 7 | Tanbonliong/Prausnitz, eScholarship 1996, Table 2 p. 18 |
| S2 | methyl acetate + PS | 323.15 | 50,000 | 5 | same |
| S2 | acetone + PMMA | 323.15 | 125,000 | 6 | same |
| S2 | methyl acetate + PMMA | 323.15 | 125,000 | 5 | same |
| S3 | 2-butanone + PMMA | 333.15 / 343.15 / 353.15 | 15,000 | 18 | Pavlicek/Bogdanic/Wichterle, CABEQ 28 (2014) 447-450, Table 2 p. 448, doi:10.15255/CABEQ.2014.19388 |

Provenance guard: the thesis table pools measurements; only rows the text reports
as new measurements of the thesis are packed (S2). The thesis table's PS-acetone
rows are credited in-source to Bawn & Wajid (Trans. Faraday Soc. 52 (1956) 1658,
paywalled) and are NOT packed.

## Binding status (all pending, deliberately)

- S1 -> `pending:polymer_pc_saft` (PC-SAFT parameters for toluene + POLY_PS exist
  in data/thermo_params/special/polymer.yaml with k_ij = 0; nothing was tuned).
- S2/S3 -> `pending:flory_huggins` (no FH chi for those pairs exists anywhere open;
  NOT FOUND this session; no pair was fitted).
- No `cases*.yaml` was touched; no V1 file was modified.

## NOT FOUND / gaps

- PIB/pentane, PE/hexane (and PIB/benzene etc.) open numeric tables with polymer
  MW stated: NOT FOUND (paywalled; see pack.yaml header for the tried URLs).
- PMMA pseudo-component registrations in this repo: NOT FOUND (only POLY_PS of
  P1-07 exists). The pack names the ids a future curation would register and
  fails loudly until then, per repo convention.
