# B-08: Agent tools + /api/agent

- **Depends on:** B-02..B-07
- **Note:** new routes change openapi.json, so this PR needs the `contract-change` label and a human merge.
  Register routes with `app.include_router(...)` in a single line added to `api/app.py`.

## Goal
Tool-calling agent over the project API: add_unit, connect, set_param, solve, read_variable, case_study, render. Uses ANTHROPIC_API_KEY from env; streams events.

## Files
- `src/ngdesign/agent/tools.py`
- `src/ngdesign/agent/loop.py`
- `src/ngdesign/api/routes_agent.py`
- `tests/agent/test_tools.py`

## Acceptance criteria
- [ ] Each tool unit-tested without the LLM
- [ ] Scripted session (fake model) builds a 2-unit flowsheet and solves it
- [ ] ruff, mypy, pytest green; openapi.json regenerated (label contract-change, human merges)
