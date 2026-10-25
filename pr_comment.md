Item-by-item response to the CHANGES REQUESTED review:

**1. Step 3 — verified V1 case or documented gap (blocking).** Recorded the gap in the filter row's notes in `data/unit_models/separation.yaml` (commit a249714), naming what was searched. The spec's candidate sources do not yield a transcribable printed input/output pair for the batch constant-pressure Ruth model with printed inputs only:

- Geankoplis, 4th ed., sect. 14.2: Examples 14.2-1 and 14.2-2 evaluate alpha and Rm by regression on t-V data, so there is no printed closed-form case to pin at rtol 1e-9. Example 14.2-4 folds the wet-cake moisture into Cs = rho*Cx/(1 - m*Cx) with m = 2 kg wet cake per kg dry cake — a moisture model different from R1's porosity-based cake — so reproducing its printed 6.66 m2 would need an unprinted cake porosity.
- The FOSSEE open transcription of Geankoplis ch. 14: its regression prints differ from the book's graphical reads (264.61 s vs the book's 269.7 s recovery time used in 14.2-3), so it is not reproducible at the required tolerance either.
- McCabe, Smith and Harriott, 7th ed., Mechanical Separations — fetched and inspected this session. Note the spec cites this as ch. 29; in the 7th edition it is ch. 30. Example 30.2 is a least-squares regression of t-V data for alpha and Rm (Table 30.3), not a closed-form case, and Example 30.3 is a continuous rotary-drum design (Eq. 30.34) with a compressible cake (alpha = alpha0/dP**0.26) and the moisture folded into the slurry concentration. Neither matches R1's batch constant-pressure form with printed inputs.

Per the review's second option the gap is recorded in the row notes rather than a reconstructed case; the level's closed-form behaviour stays covered by the CF1-CF4 tests (rtol 1e-9) and the R0-reduction identity test.

**2. Refusal tests must pin the exception classes.** Done in tests/units/separation/test_filter_r1.py (commit a249714): `test_no_cake_component_flows` now expects `pytest.raises(FilterR1SpecError, match="cake_fractions")`, and `test_r0_spec_error_propagates` now expects `pytest.raises(FilterSpecError, match="not in the feed")` — confirming the R0 refusal propagates uncaught as FilterSpecError. All 24 tests in the R1 suite pass on the pushed head.

**3. Docstring — partially cake-sent components.** Done in src/ngdesign/units/separation/filter_r1.py (commit a249714): the module docstring now states that a cake component sent only partly to the cake (fraction < 1) leaves its remainder in the filtrate untouched by the moisture move, and that f_m applies only to the non-cake components (spec step 4 of the algorithm).

Branch state: u-lv/filter merged origin/main (d000067) and regenerated the unit docs (a2401d5); validate_units exits 0 with the audit clean, ruff check/format clean on the touched files. CI is running on a2401d5.
