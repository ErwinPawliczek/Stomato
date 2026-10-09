# S-40: Native Peng-Robinson cross-check

- **Wave:** stretch
- **Depends on:** S-01
- **Plugin:** none (library + tests)

## Goal
Independent PR implementation to cross-validate the wrapper.

## Files (create only these)
- `src/ngdesign/thermo/pr_native.py`
- `tests/thermo/test_pr_native.py`

## Method
PR EOS with van der Waals mixing, Rachford-Rice with Wilson K init, successive substitution. Constants from ngdesign.data.components(). Not registered as `pr`; register as `pr_native`.

## Acceptance criteria
- [ ] Z factor and vapor fraction agree with `pr` within 1% on 10 random gas compositions (hypothesis)
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Three-phase.
