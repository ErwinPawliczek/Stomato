# S-33: P&ID builder from solved flowsheet

- **Wave:** 2
- **Depends on:** S-20, S-30, S-31, S-32
- **Plugin:** kind `pid_builder`, name `default`

## Goal
Generate the bare PID (equipment, nozzles, numbered lines) from a SolvedFlowsheet.

## Files (create only these)
- `src/ngdesign/pid_rules/builder.py`
- `tests/pid_rules/test_builder.py`

## Method
Equipment from datasheets (run registered sizers for each unit kind; skip units with no sizer
and give them default nozzles per port). One PidLine per stream: size by line_size; fluid code from
StreamSpec.service; pipe class: D1 if design P > 5.1 MPa (cl300 CS limit at 100 F is 740 psig), L1 if
T < 244 K, S1 for amine/sour, else B1; number `<nps>"-<fluid>-<seq>-<class>` with seq from 1001 in stream
order. Ends: equipment nozzle whose `port` matches the stream port, or boundary label for feeds/products.
Design P/T from the connected equipment (max of the two ends).

## Acceptance criteria
- [ ] Own tests: builder output for the solved slice validates as PID; every stream has exactly one line; every registered pid_rule then applies cleanly (check == [])
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Rules themselves.
