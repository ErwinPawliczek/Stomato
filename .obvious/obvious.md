# ngdesign
Natural gas processing design software: a Peng-Robinson simulation drives sizing, PFD, P&ID, 3D piping
routing and isometric drawings, all generated from one Project model (src/ngdesign/contracts/project.py).
Backend is Python (src/ngdesign, FastAPI in src/ngdesign/api). Frontend is React/TS in frontend/.

Constraints for automated work:
- One executable = one spec from specs/backend/ or specs/frontend/ = new files only. Read AGENTS.md
  (backend) or frontend/AGENTS.md (frontend) first. Never mix frontend/ and backend changes in one PR.
- Locked (human-owned): src/ngdesign/contracts/, registry.py, data.py, data/, tests/golden/test_*,
  tests/property/, tests/contracts/, openapi.json, .github/. CI rejects PRs touching them.
- Correctness comes from oracle tests (data/golden/*.yaml, CoolProp cross-checks, balance and invariant
  tests). Never weaken, skip or loosen a test to get green. Done = the spec's named tests PASS, not skip.
