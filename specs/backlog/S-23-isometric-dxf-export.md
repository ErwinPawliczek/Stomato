# S-23: Isometric DXF export

- **Wave:** 1
- **Depends on:** S-19
- **Plugin:** kind `diagram`, name `iso_dxf`

## Goal
Export the same isometric geometry to DXF for CAD users.

## Files (create only these)
- `src/ngdesign/render/isometric_dxf.py`
- `tests/render/test_isometric_dxf.py`

## Method
Use `ezdxf`. render(obj) takes a RoutedLine and returns the DXF document as a string
(`doc.write` to StringIO). Same projection as S-19 (import its projection function). Layers: PIPE, FITTING,
WELD, DIM, TEXT. Dimensions as real DXF dimension entities on DIM.

## Acceptance criteria
- [ ] Round-trip: ezdxf reads the string; count of LINE entities on PIPE equals PIPE components
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Title block graphics.
