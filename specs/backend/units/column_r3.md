# column R3: rate-based distillation and Murphree-efficiency stages

- **Family / package:** column, `src/ngdesign/units/column/` (the R2 package of this row).
- **Levels delivered:** R3, from absent to `provisional`; `end_state` moves from R2 to R3
  (plan §2 U-E 2: "rate-based stages, Murphree/vaporisation efficiencies").
- **Contract change:** no.
- **Owned files:**
  - `src/ngdesign/units/column/rate_based.py` (extended: condenser end, Murphree trays)
  - `src/ngdesign/units/column/rate_based_units.py` (`_info` generalised to the stage kinds)
  - `src/ngdesign/units/column/column_r3.py` (new adapter `ColumnR3`)
  - `tests/units/column/test_column_r3.py` (new)
  - `data/unit_models/column.yaml`: `levels.R3` of row `column`, `end_state`, `notes`
- **Read-only:** `ngdesign.units.column.Column` (R2, the reduction oracle),
  `_zero_flow_state` (the R2 placeholder for the unused `side_draw` port). Nothing in
  `inside_out.py`, `naphtali_sandholm.py`, `graph_ns.py`, `relaxation.py` is edited.

## Method
One simultaneous Newton (the existing `solve_rate_based`: inside-out on the property
models, block-tridiagonal finite-difference Jacobian) over a stack of stage blocks, top to
bottom. Two new block kinds join the existing packed segment and kettle:

| kind | unknowns | equations |
|---|---|---|
| `partial` condenser (equilibrium) | v, l (c each), T | `v + l - v_in - f = 0`; `v/V - K(T) l/L = 0`; one top spec |
| `total` condenser | d, l (c each), T | `d + l - v_in = 0`; `l_i/L - d_i/D = 0` (i < c); `sum K_i(T) l_i/L - 1 = 0` (saturated condensate, bubble point); one top spec |
| `rate` packed segment | unchanged (Krishna-Taylor, 5c+3) | unchanged |
| `tray` (Murphree) | v, l (c each), T | `v + l - v_in - l_in - f = 0`; `v/V - y_in - E (K(T) l/L - y_in) = 0`; `H_V + H_L - H_Vin - H_Lin - H_f = 0` |
| `kettle` | unchanged (2c+1) | unchanged; one bottom spec |

`y_in` is the vapour entering the tray (`v_{j+1}` plus any vapour feed to the tray,
normalised), the convention `murphree_vapour` already reports. The Murphree row is
Murphree (1925), Ind. Eng. Chem. 17, 747-750: `y_n = y_{n+1} + E_MV (y*_n - y_{n+1})`,
with `y*_n = K_n x_n` and `K` the package's `phi_L/phi_V` anchored at `(x_n, y*_n)` (a
fixed point on `y* = norm(K x)`, the incipient vapour), not at the actual tray vapour.
Summing the c rows gives `E (sum K x - 1) = 0`, i.e. each tray sits at its liquid bubble
point; both phases leave at the tray `T` (the standard Murphree MESH stage).

Top specs: `reflux_ratio` (L/D), `distillate_rate` (D, mol/s), `condenser_duty_W`
(heat removed, W); `bottoms_rate` is placed on the top as `D = F - B` (exact at
convergence: the component balances sum to `D + B = F`). Bottom specs: the existing
`KETTLE_SPECS`. Exactly two specs, one per end; pairs with no valid split
(e.g. `distillate_rate` + `bottoms_rate`, two top-only specs) refuse.

Vaporisation efficiency (Holland) is **omitted**: its defining equation number could not
be verified from an accessible copy, so it is not implemented (AGENTS.md: never invent).

## Params (`ColumnR3`)
Common: `n_stages` (int >= 3, R2 numbering: stage 1 the partial condenser or the tray
under the total condenser, stage N the kettle), `condenser` (`total` | `partial`),
`reboiler` (`kettle` only, optional), `feed_stage` (1..N; 2..N-1 for rate-based),
`pressure_profile` (scalar or N values, Pa; total condenser at stage 1's pressure),
`specs` (two keys), `stage_model` (`rate_based` default | `murphree`).
`rate_based`: the six packing keys of the absorber R3 (`column_diameter_m`,
`packed_height_m` split equally over the N-1 (total) or N-2 (partial) segments,
`nominal_size_m`, `specific_area_m2_m3`, `critical_surface_tension_N_m`,
`surface_tension_N_m`) and `transfer_factor` (default 1).
`murphree`: `murphree_efficiency`, a number in (0, 1] or one per tray (stages between
condenser and kettle: N-1 total, N-2 partial), default 1.

## Reduction limits
- `murphree`, E = 1: the equations are R2's MESH stage for stage; with R2's achieved specs
  as inputs the result equals R2 to R2's own convergence (partial condenser; R2 returns a
  total condenser's reflux at the stage-1 temperature, R3 at its bubble point, so the
  total-condenser comparison carries that convention difference and is stated measured).
- `rate_based`, `transfer_factor` -> infinity: each segment becomes an equilibrium stage;
  measured deviation from R2 stated in the test.

## Tests (`tests/units/column/test_column_r3.py`)
1. Murphree E=1 == R2 (partial condenser, R2's achieved specs), measured.
2. Rate-based transfer_factor 1e4 -> R2 (same stages), measured.
3. Closed form: total condenser `L = R D`, `x_D = y_1`, `Q_c = V_1 (h_V(y_1,T_V1) - h_L(x_D, T_bub))`;
   Murphree `y_n = y_{n+1} + E (y*_n - y_{n+1})` recomputed from an independent
   `bubble_point` on a binary tray.
4. Refusals: `RateBasedSpecError`, `pytest.raises(match=...)` per parameter.
5. V0 on `example_case` (component and energy 1e-8) and `tests/property/test_unit_balances.py`.

## Steps
1. This plan. 2. Extend `rate_based.py` (stage kinds, condenser blocks, Murphree trays,
spec placement, seed). 3. `ColumnR3` + tests. 4. Catalogue R3 + docs regeneration.
