"""The new-project template catalogue."""

from __future__ import annotations

import importlib
import sys
import types

import pytest

from ngdesign.flowsheets import templates as catalogue
from ngdesign.flowsheets.templates import BLANK, template, templates


def test_catalogue_ids_are_unique_and_blank_comes_first() -> None:
    ids = [t.id for t in templates()]
    assert ids[0] == BLANK
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("template_id", [t.id for t in templates()])
def test_every_template_builds_a_flowsheet(template_id: str) -> None:
    chosen = template(template_id)
    assert chosen is not None
    flowsheet = chosen.build()
    tags = [u.tag for u in flowsheet.units]
    assert len(tags) == len(set(tags))
    assert chosen.build() == flowsheet  # deterministic: a fresh copy per call


def test_sample_templates_delegate_to_their_module() -> None:
    for tid in ("slice", "amine_loop", "mea_amine_loop"):
        chosen = template(tid)
        assert chosen is not None
        module = importlib.import_module(f"ngdesign.flowsheets.{tid}")
        assert chosen.build() == module.build()


def test_unknown_template_is_none() -> None:
    assert template("no-such-template") is None


def test_optional_template_appears_once_its_module_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    """The trace demo template is listed only when ngdesign.flowsheets.trace_demo
    imports; a stand-in module proves the wiring without the real one."""
    from ngdesign.contracts import Flowsheet

    name = "ngdesign.flowsheets.trace_demo"
    if name not in sys.modules and importlib.util.find_spec(name) is None:
        assert template("trace_demo") is None
    fake = types.ModuleType(name)
    fake.__doc__ = "'Trace demo: gas processing' - a small gas-plant front end for provenance review."
    fake.NAME = "Trace demo: gas processing"  # type: ignore[attr-defined]
    fake.build = lambda: Flowsheet(name="trace", units=[], streams=[])  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, name, fake)
    chosen = template("trace_demo")
    assert chosen is not None
    assert chosen.title == "Trace demo: gas processing"
    assert chosen.description == "A small gas-plant front end for provenance review"
    assert chosen.build().name == "trace"


def test_a_broken_optional_module_is_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(name: str) -> types.ModuleType:
        raise ModuleNotFoundError("No module named 'some_dependency'", name="some_dependency")

    monkeypatch.setattr(importlib, "import_module", broken)
    with pytest.raises(ModuleNotFoundError):
        catalogue._optional("trace_demo", "trace_demo")
