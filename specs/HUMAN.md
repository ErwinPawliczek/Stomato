# Human tasks (not for agents)

These touch locked paths (`data/`) or need judgement. Do them yourself or with the domain expert.

- **H-01 Fitting and valve dimensions:** add `data/flange_dims_b165.csv` (NPS, class, WN flange length, RF/RTJ),
  `data/valve_f2f_b1610.csv` (type, NPS, class, face-to-face mm), `data/fittings_b169.csv` (LR/SR elbow, tee,
  reducer centre-to-end). Then add loader functions in `ngdesign/data.py` (label PR `contract-change`).
- **H-02 Velocity / pressure-drop limits:** confirm or replace the S-20 table.
- **H-03 Verify** `data/flanges_b165.csv` and allowable stresses in `data/pipe_classes.yaml` against the codes.
- **H-04 Sizing constants:** Souders-Brown K, retention times, U values flagged VERIFY in S-31/S-32.
- **H-05 Slice basis:** sanity-check `flowsheets/slice.py` inlet composition, pressures, TEG rate.
