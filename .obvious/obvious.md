# Stomato (package `ngdesign`)
Open, modular steady-state process simulator plus engineering deliverables (sizing, PFD, P&ID,
piping routing, isometrics) generated from one Project model (src/ngdesign/contracts/project.py).
Backend is Python (src/ngdesign, FastAPI in src/ngdesign/api). Frontend is React/TS in frontend/.
Architecture and roadmap: docs/PLAN.md.

Constraints for automated work:
- One executable = one spec from specs/backend/ or specs/frontend/. Read AGENTS.md (backend) or
  frontend/AGENTS.md (frontend) first. Never mix frontend/ and backend changes in one PR.
- A spec names the packages it may edit. Edit existing files there when told; never duplicate a
  function to avoid editing its owner. Reuse registered plugins.
- Dependency direction is enforced by `.importlinter` (`uv run lint-imports`). Never add an
  ignore_imports line.
- Locked (orchestrator-owned): tests/golden/test_*, tests/property/, data/golden/, .github/,
  AGENTS.md, pyproject.toml, uv.lock. Contracts only when the spec says `Contract change: yes`.
- Correctness comes from oracle tests (data/golden/*.yaml, CoolProp cross-checks, balance and
  invariant tests, byte-identical e2e outputs). Never weaken, skip or loosen a test to get green.
  Done = the spec's acceptance criteria are true and CI is green.
- When the PR is open, comment its URL on the GitHub issue named in the task. If blocked, comment
  the blocker there and stop.
- Never merge, approve or enable auto-merge on your PR, and never push to `main`: the orchestrator
  reviews and merges (branch protection requires an approving review).
