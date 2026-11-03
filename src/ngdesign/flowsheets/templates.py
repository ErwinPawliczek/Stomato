"""Project templates: the flowsheets a new project can start from.

A template is a named builder over one of the sample flowsheet modules in this
package (plus the blank flowsheet). The catalogue is read by the API's
"new project" route; nothing here holds numbers of its own — every template
delegates to its module's ``build()``.

Optional templates (``_OPTIONAL``) are modules that land on other branches
(the provenance trace demo): when the module is not importable the template is
simply absent, and it appears without code changes once the module exists.
Only a missing module is tolerated — any other import error propagates.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass

from ngdesign.contracts import Flowsheet

BLANK = "blank"


@dataclass(frozen=True)
class Template:
    """One entry of the new-project catalogue."""

    id: str
    title: str
    description: str
    build: Callable[[], Flowsheet]


def _blank() -> Flowsheet:
    return Flowsheet(name="blank", units=[], streams=[])


def _module_build(module: str) -> Callable[[], Flowsheet]:
    def build() -> Flowsheet:
        mod = importlib.import_module(f"ngdesign.flowsheets.{module}")
        flowsheet: Flowsheet = mod.build()
        return flowsheet

    return build


#: (template id, module, title, description) of the always-present samples.
_SAMPLES: tuple[tuple[str, str, str, str], ...] = (
    (
        "slice",
        "slice",
        "Gas dehydration slice",
        "Inlet 3-phase separator, compressor, air cooler and TEG contactor; condensate pump and heater.",
    ),
    (
        "amine_loop",
        "amine_loop",
        "MDEA amine loop",
        "Sour-gas absorber and regenerator with lean-solvent recycle (MDEA).",
    ),
    (
        "mea_amine_loop",
        "mea_amine_loop",
        "MEA amine loop",
        "The amine loop with aqueous MEA as the solvent.",
    ),
)

#: (template id, module) of templates whose module may not exist yet. Title is
#: the module's ``NAME``; description the first line of its docstring.
_OPTIONAL: tuple[tuple[str, str], ...] = (("trace_demo", "trace_demo"),)


def _optional(template_id: str, module: str) -> Template | None:
    qualified = f"ngdesign.flowsheets.{module}"
    try:
        mod = importlib.import_module(qualified)
    except ModuleNotFoundError as exc:
        if exc.name != qualified:
            raise
        return None
    doc = (mod.__doc__ or "").strip().splitlines()
    title = str(getattr(mod, "NAME", template_id))
    description = doc[0] if doc else title
    if " - " in description and description.startswith(f"'{title}'"):
        description = description.split(" - ", 1)[1]
        description = description[:1].upper() + description[1:]
    return Template(template_id, title, description.rstrip("."), _module_build(module))


def templates() -> list[Template]:
    """The catalogue: blank first, then the samples, then optional templates present."""
    out = [Template(BLANK, "Blank flowsheet", "An empty flowsheet: add units and streams yourself.", _blank)]
    out += [Template(tid, title, desc, _module_build(mod)) for tid, mod, title, desc in _SAMPLES]
    out += [t for tid, mod in _OPTIONAL if (t := _optional(tid, mod)) is not None]
    return out


def template(template_id: str) -> Template | None:
    """One template by id, or None when the catalogue has no such id."""
    return next((t for t in templates() if t.id == template_id), None)
