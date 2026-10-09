---
description: Branch, commit, open a PR and enable auto-merge
---
1. If on main: `git switch -c fe/<short-slug-of-the-change>`.
2. In frontend/: npm run typecheck && npm run lint && npm test && npm run build. Stop if anything fails.
3. Stage and commit only files under frontend/ with a clear message.
4. `git push -u origin HEAD`, then `gh pr create --fill --label frontend`, then `gh pr merge --auto --squash`.
5. Print the PR URL. Then `git switch main && git pull`.
