"""Refining unit adapters (spec U-H1): assay feeder, desalter, crude and
vacuum columns, preflash drum and product blender, at catalogue rigour R0.

The shared sharp-cut machinery lives in ``_cuts``; the stored-assay slate
accessors live in ``slate``. Registration comes from the catalogue YAML
(``data/unit_models/refining.yaml`` adapter paths, applied by
``units.catalogue.register_all``); no module carries a ``@register``
decorator (U-R1 round-1 conventions).
"""
