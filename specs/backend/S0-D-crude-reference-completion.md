# S0-D: Complete the S0 crude-unit reference with printed, citable data

- **Phase:** Unit catalogue round 2 (slice S0), data task, in parallel with S0-1.
- **Depends on:** A-01 (merged #195).
- **Packages you may edit:** `data/validation_units/refining/s0_reference.yaml`, `data/assays/` (new files only, with citations), `docs/` (a findings note), `tests/data/` (schema and consistency tests for what you add).
- **Never edit:** any `src/` code, `data/unit_models/`, any other validation cases.
- **GitHub issue:** #236
- **Contract change:** no. **Benchmark delta expected:** none.

## Goal
S0's reference must let a flowsheet be checked against printed numbers. The committed `s0_reference.yaml` (Bagajewicz & Ji 2001, Ind. Eng. Chem. Res. 40, 617) holds the assay, the feed rate (795 m3/h) and the product D86 95 % points. It does not hold:
- product yields or rates;
- stage counts;
- the number of side strippers;
- pumparound duties (it says one top pumparound circuit; the plan says two);
- stripping-steam rates;
- flash-zone T and P;
- any vacuum-column data.

`specs/INDEX.md` notes "round 2 needs a yields source (Part II)".

## Work
1. Find the missing numbers in open, citable, printed sources, in this order:
   - Bagajewicz & Ji 2001 Part I and its companion Part II;
   - Bagajewicz's later papers on the same unit;
   - other open crude-unit design papers that print a complete unit (for example the Ji & Bagajewicz heat-integration papers, or Inamdar, Gupta & Saraf 2004);
   - Watkins, *Petroleum Refinery Distillation*, if the needed pages are open.
2. For every number added, record:
   - the source, edition, table or figure, and page;
   - the printed value in printed units, beside its SI conversion.

   Only values read from a printed table or text are allowed. Never digitise a chart, never back-solve a value, and never take a number from a simulator output (Aspen, HYSYS, PRO/II, DWSIM) unless the paper itself prints it as its published result.
3. If the unit is completed from a second source, the second source must describe the same unit (same crude, same feed rate). Otherwise, propose replacing the S0 reference with a single source that prints a complete unit (assay, configuration and product rates), and give its full citation. **Do not mix units.**
4. Resolve the pumparound count (one or two) from the source, and record it.

## Deliverable
- The updated `s0_reference.yaml`, with a consistency test (rates sum to the feed within the printed rounding; D86 points ascending).
- A findings note in `docs/` listing what was searched, what was found, and what is still missing, with a recommendation.
- If any required item cannot be found, the PR says so plainly. The orchestrator then decides between the reference and a replacement. Comment the findings on the issue.
