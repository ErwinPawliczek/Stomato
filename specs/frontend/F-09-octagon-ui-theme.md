# F-09: Stomato octagon UI theme and app shell

- **Depends on:** none (first implemented in PR #69)
- **Rules:** frontend/AGENTS.md

## Goal
One visual language for every Stomato screen, so views built by different agents look like one product.
The reference designs are reviewed and approved. Match them; do not invent new styles.

## Reference
- `specs/frontend/design/stomato-screens.html`: the app screens (open it in a browser). It covers
  Home, Equipment, Sheet, Agent and the project pages.
- `specs/frontend/design/stomato-themes.html`: the theme kit: palettes, octagon controls, dropdown,
  scroll bars, progress.
- Live code: `frontend/src/theme/` (palettes, `kit.css`), `frontend/src/components/`, `frontend/src/styles.css`.

## Rules
- **Shape.** Every box, button, input, chip, tab and scroll thumb is an octagon. Use the kit:
  class `ob` for a bordered octagon (it draws `--obLine` and `--obFill`), or `clip-path: var(--oct)`
  for a flat one. Set the corner cut with `--c`. Never use `border-radius`.
- **Colour.** Only palette tokens (`--bg`, `--surface`, `--surface2`, `--ink`, `--muted`, `--line`,
  `--accent`, `--accent2`, `--accent3`, `--ok`, `--warn`, `--bad`, ...) from `theme/palettes.ts`.
  No hex colours in views. Palettes: Permian (light, default), Blueprint (dark), Mint Graphite (light).
- **Type.** Chakra Petch for all text (700 for titles, 400 for body). JetBrains Mono only for numbers,
  tags, code and units.
- **Buttons.** `btn ob` with the press-in shadow; `btn ob primary` for the main action.
- **Dropdowns.** `components/Dropdown.tsx` (interlocking octagon pieces with diamond fillers),
  not a styled native `<select>`, for new menus.
- **Scrolling.** Scrollable tables and grids go in `components/OctScroll.tsx` (octagon thumbs in their
  own gutter, no visible rail).
- **Navigation.**
  - The left rail holds the logo (the only place the word "Stomato" appears), Home, Equipment, Sheet,
    Agent and the palette switch.
  - Global pages have no top bar.
  - Inside a project the top bar shows the project name, a one-line summary, Close, and the tabs
    Flowsheet, Results and Drawings.
  - Drawings has the sub-tabs PFD, P&ID, Plot plan and Isometrics.
- **Equipment page.** Diagonally stacked regular octagons on a 45° checkerboard, with no filler squares.
  The tile width is about the page width ÷ 6, clamped to 150–230 px. A clicked tile opens into a big
  octagon about three tiles wide; Esc closes it.
- **Progress.** Octagon cells filling one by one. For long runs, a stage chain plus a time-share bar
  that tags the slowest stage.

## Planned (from the designs, not built yet)
- Thermo dropdown (PR, PR78, SRK, NRTL; GERG-2008 planned) and a Units dropdown (SI or Field) in the
  project top bar, plus Solve with the progress cells.
- A Datasheets project tab, once the sizer datasheets have an endpoint.
- Redesigned Flowsheet, Results and Drawings internals. They are only restyled today.

## Acceptance criteria (for any frontend PR after this one)
- [ ] New UI uses kit classes and palette tokens only. It looks right in all three palettes.
- [ ] Matches the reference designs for the page it touches.
- [ ] typecheck, lint, test, build green
- [ ] Only files under frontend/ changed (spec/design updates go in their own PR)
