# S-43: Deethanizer shortcut (Fenske-Underwood-Gilliland)

- **Wave:** stretch
- **Depends on:** S-01
- **Plugin:** kind `unit`, name `deethanizer`

## Goal
Shortcut column for NGL.

## Files (create only these)
- `src/ngdesign/units/deethanizer.py`
- `tests/units/test_deethanizer.py`

## Method
Fenske N_min, Underwood theta and R_min, Gilliland (Eduljee) N at R = 1.3 R_min, Kirkbride feed stage; splits by Fenske distribution; condenser/reboiler duties by energy balance.

## Acceptance criteria
- [ ] test_unit_balances passes
- [ ] Own test reproduces a textbook FUG example (cite it) within 5%
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Rigorous trays.
