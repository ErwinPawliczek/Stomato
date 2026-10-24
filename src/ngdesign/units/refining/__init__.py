"""Refining unit adapters: assay feeder, desalter, crude and vacuum
columns, preflash drum and product blender (spec U-H1) plus mass-only
reactor rows `reactors_coker`, `reactors_reformer` and `reactors_hdt`
(spec U-H2), at catalogue rigour R0/R1.

The shared sharp-cut machinery lives in ``_cuts``; the stored-assay slate
accessors live in ``slate``. Registration comes from the catalogue YAML
(``data/unit_models/refining.yaml`` adapter paths, applied by
``units.catalogue.register_all``); no module carries a ``@register``
decorator (U-R1 round-1 conventions). The U-H2 reactor modules register
their pseudo lumps at import (the catalogue loader imports adapters by
``module:ClassName`` string, so registration is definitional data, not
plugin state).
"""
