# S-20: Line sizing by service velocity limits

- **Wave:** 0
- **Depends on:** none
- **Plugin:** kind `correlation`, name `line_size` (no golden file; own tests)

## Goal
Choose the NPS for a line from flow, density and service.

## Files (create only these)
- `src/ngdesign/sizing/line_size.py`
- `tests/sizing/test_line_size.py`

## Method
Candidate NPS list [1,1.5,2,3,4,6,8,10,12,14,16,18,20,24], schedule 40 ID from
`ngdesign.data.pipe`. Limits (initial values, flagged `# VERIFY with process engineer`):
- gas (PG): v <= 18 m/s and rho*v^2 <= 6000 Pa, and v <= 0.8 * API 14E erosional velocity
- liquid pump suction: 0.6-1.5 m/s; pump discharge / general liquid (PL): 1-3 m/s; water (W) same as PL
- glycol (GL): <= 1.5 m/s
Pick the smallest NPS satisfying the max limits. Return dict: nps_in, velocity_m_s, rho_v2, limit_hit.
Keep the limits table in one module-level dict so it can be swapped later.

## Acceptance criteria
- [ ] Own tests: 50 MMSCFD gas at 3.4 MPa (rho about 28 kg/m3) gives NPS 8 to 12; a 0.02 m3/s liquid discharge gives NPS 3 to 4; monotonic (more flow never gives a smaller pipe)
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Two-phase lines (not in v1).
