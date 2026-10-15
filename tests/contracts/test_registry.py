"""Registry behaviour. LOCKED."""

import pytest

from ngdesign import registry


def test_discover_imports_everything() -> None:
    registry.discover()  # must not raise: every plugin module must import cleanly


def test_unknown_kind_rejected() -> None:
    with pytest.raises(ValueError):
        registry.register("nope", "x")


def test_duplicate_name_rejected() -> None:
    @registry.register("correlation", "_dup_test")
    class A: ...

    with pytest.raises(ValueError):

        @registry.register("correlation", "_dup_test")
        class B: ...
