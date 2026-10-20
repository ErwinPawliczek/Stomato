"""Graph-layout helpers shared by the diagram renderers (spec P0-05).

Single home for the longest-path layering previously duplicated between
``pfd_svg.py`` (S-22) and ``pid_svg.py`` (S-18). Each renderer keeps its own
``_layout`` (different inputs) but builds plain tag/edge lists and calls
``topological_layers`` here.
"""

from __future__ import annotations

__all__ = ["topological_layers"]


def topological_layers(nodes: list[str], edges: list[tuple[str, str]]) -> dict[str, int]:
    """Longest-path layering via Kahn's algorithm; cycle leftovers go last.

    ``nodes`` are the tag names, ``edges`` directed (u, v) pairs with both ends
    in ``nodes``. Returns tag -> layer index, layer 0 for every source.
    """
    succ: dict[str, set[str]] = {t: set() for t in nodes}
    indeg: dict[str, int] = {t: 0 for t in nodes}
    for u, v in edges:
        if v not in succ[u]:
            succ[u].add(v)
            indeg[v] += 1
    layer = {t: 0 for t in nodes}
    queue = sorted(t for t in nodes if indeg[t] == 0)
    done: set[str] = set()
    while queue:
        n = queue.pop(0)
        done.add(n)
        for m in sorted(succ[n]):
            layer[m] = max(layer[m], layer[n] + 1)
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    # Nodes caught in a cycle never reach indeg 0: park them after the last layer.
    max_layer = max(layer.values(), default=0)
    for t in nodes:
        if t not in done:
            layer[t] = max_layer + 1
    return layer
