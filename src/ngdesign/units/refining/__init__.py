"""Refining unit adapters (spec U-H1): assay feeder, desalter, crude and
vacuum columns, preflash drum and product blender, at catalogue rigour R0.

The shared sharp-cut machinery lives in ``_cuts``; the stored-assay slate
accessors live in ``slate``. Modules self-register their ``@register("unit",
...)`` adapters; the catalogue discovers them by walking this package.
"""
