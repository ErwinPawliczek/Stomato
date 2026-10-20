"""Tests for the shared render graph layering (spec P0-05)."""

from __future__ import annotations

from ngdesign.render._graph import topological_layers


def test_linear_chain() -> None:
    layers = topological_layers(["a", "b", "c"], [("a", "b"), ("b", "c")])
    assert layers == {"a": 0, "b": 1, "c": 2}


def test_diamond_bands_by_longest_path() -> None:
    layers = topological_layers(["a", "b", "c", "d"], [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")])
    assert layers == {"a": 0, "b": 1, "c": 1, "d": 2}


def test_duplicate_edges_counted_once() -> None:
    once = topological_layers(["a", "b"], [("a", "b")])
    twice = topological_layers(["a", "b"], [("a", "b"), ("a", "b")])
    assert twice == once == {"a": 0, "b": 1}


def test_cycle_nodes_park_after_the_last_layer() -> None:
    # a <-> b never reach indegree 0; c is a plain source.
    layers = topological_layers(["a", "b", "c"], [("a", "b"), ("b", "a")])
    assert layers == {"c": 0, "a": 1, "b": 1}


def test_nodes_without_edges_sit_at_layer_zero() -> None:
    layers = topological_layers(["a", "b"], [])
    assert layers == {"a": 0, "b": 0}


def test_empty_graph() -> None:
    assert topological_layers([], []) == {}
