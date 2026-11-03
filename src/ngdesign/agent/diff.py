"""Structured diff between two projects (docs/agentic-layer.md section 3).

Pure: two :class:`~ngdesign.contracts.Project` bodies in, a JSON-serialisable
dict out naming exactly what changed — units added/removed/changed (param-level
``from``/``to``), streams added/removed/changed (flattened field paths), the
thermo package, the component slate, design specs and layout moves. Only
non-empty sections appear, so an empty dict means "no change". The agent panel
renders it under each tool call; the change feed carries it for every edit.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import Project

Diff = dict[str, Any]


def _flat(value: Any, prefix: str = "") -> dict[str, Any]:
    """Nested dicts flattened to dotted paths; lists and scalars are leaves."""
    if isinstance(value, dict) and value:
        out: dict[str, Any] = {}
        for key in sorted(value):
            path = f"{prefix}.{key}" if prefix else str(key)
            out.update(_flat(value[key], path))
        return out
    return {prefix: value} if prefix else {}


def _field_changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    a, b = _flat(before), _flat(after)
    return {
        path: {"from": a.get(path), "to": b.get(path)}
        for path in sorted(set(a) | set(b))
        if a.get(path) != b.get(path)
    }


def _keyed(
    before: list[dict[str, Any]], after: list[dict[str, Any]], key: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Added, removed and changed entries of two lists keyed by ``key``."""
    old = {item[key]: item for item in before}
    new = {item[key]: item for item in after}
    added = [new[k] for k in sorted(set(new) - set(old))]
    removed = [old[k] for k in sorted(set(old) - set(new))]
    changed = []
    for k in sorted(set(old) & set(new)):
        fields = _field_changes(
            {f: v for f, v in old[k].items() if f != key}, {f: v for f, v in new[k].items() if f != key}
        )
        if fields:
            changed.append({key: k, "fields": fields})
    return added, removed, changed


def _section(added: list[Any], removed: list[Any], changed: list[Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if added:
        out["added"] = added
    if removed:
        out["removed"] = removed
    if changed:
        out["changed"] = changed
    return out


def project_diff(before: Project, after: Project) -> Diff:
    """What changed from ``before`` to ``after`` (empty dict: nothing)."""
    a = before.model_dump(mode="json")
    b = after.model_dump(mode="json")
    fa, fb = a["flowsheet"], b["flowsheet"]
    diff: Diff = {}
    if a["name"] != b["name"]:
        diff["name"] = {"from": a["name"], "to": b["name"]}

    added, removed, changed = _keyed(fa["units"], fb["units"], "tag")
    units = _section(
        [{"tag": u["tag"], "kind": u["kind"], "params": u["params"]} for u in added],
        [{"tag": u["tag"], "kind": u["kind"]} for u in removed],
        changed,
    )
    if units:
        diff["units"] = units

    added, removed, changed = _keyed(fa["streams"], fb["streams"], "id")
    streams = _section(added, [{"id": s["id"]} for s in removed], changed)
    if streams:
        diff["streams"] = streams

    if fa.get("thermo") != fb.get("thermo"):
        diff["thermo"] = {"from": fa.get("thermo"), "to": fb.get("thermo")}

    def _ids(refs: list[Any]) -> set[str]:
        return {r if isinstance(r, str) else str(r.get("id")) for r in refs}

    comp_a, comp_b = _ids(fa.get("components", [])), _ids(fb.get("components", []))
    if comp_a != comp_b:
        diff["components"] = _section(sorted(comp_b - comp_a), sorted(comp_a - comp_b), [])

    added, removed, changed = _keyed(fa.get("design_specs", []), fb.get("design_specs", []), "id")
    specs = _section(added, [{"id": s["id"]} for s in removed], changed)
    if specs:
        diff["design_specs"] = specs

    for field in ("solver_options", "reactions"):
        if fa.get(field) != fb.get(field):
            changes: dict[str, Any] = _field_changes({"v": fa.get(field)}, {"v": fb.get(field)})
            diff[field] = changes or {"changed": True}

    moves: list[dict[str, Any]] = []
    for view in sorted(set(a["layout"]) | set(b["layout"])):
        la, lb = a["layout"].get(view) or {}, b["layout"].get(view) or {}
        for key in sorted(set(la) | set(lb)):
            if la.get(key) != lb.get(key):
                moves.append({"view": view, "key": key, "from": la.get(key), "to": lb.get(key)})
    if moves:
        diff["layout"] = moves
    return diff


def diff_lines(diff: Diff) -> list[str]:
    """One human line per change, for logs and plain-text surfaces."""
    lines: list[str] = []
    if "name" in diff:
        lines.append(f"project renamed {diff['name']['from']!r} -> {diff['name']['to']!r}")
    units = diff.get("units", {})
    lines += [f"+ unit {u['tag']} ({u['kind']})" for u in units.get("added", [])]
    lines += [f"- unit {u['tag']} ({u['kind']})" for u in units.get("removed", [])]
    for u in units.get("changed", []):
        for path, ft in u["fields"].items():
            lines.append(f"~ {u['tag']}.{path}: {ft['from']!r} -> {ft['to']!r}")
    streams = diff.get("streams", {})
    lines += [f"+ stream {s['id']}" for s in streams.get("added", [])]
    lines += [f"- stream {s['id']}" for s in streams.get("removed", [])]
    for s in streams.get("changed", []):
        for path, ft in s["fields"].items():
            lines.append(f"~ {s['id']}.{path}: {ft['from']!r} -> {ft['to']!r}")
    if "thermo" in diff:
        lines.append(f"~ thermo: {diff['thermo']['from']} -> {diff['thermo']['to']}")
    comps = diff.get("components", {})
    lines += [f"+ component {c}" for c in comps.get("added", [])]
    lines += [f"- component {c}" for c in comps.get("removed", [])]
    specs = diff.get("design_specs", {})
    lines += [f"+ design spec {s['id']}" for s in specs.get("added", [])]
    lines += [f"- design spec {s['id']}" for s in specs.get("removed", [])]
    lines += [f"~ design spec {s['id']}" for s in specs.get("changed", [])]
    for field in ("solver_options", "reactions"):
        if field in diff:
            lines.append(f"~ {field}")
    for m in diff.get("layout", []):
        lines.append(f"~ layout.{m['view']}[{m['key']}]: {m['from']} -> {m['to']}")
    return lines


__all__ = ["Diff", "diff_lines", "project_diff"]
