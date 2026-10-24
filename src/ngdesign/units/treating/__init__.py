"""Gas-treating and specialty unit adapters (spec U-G, catalogue round 1).

R0 adapters for the ``treating`` family rows that have no adapter of their own
yet: ``teg_regen`` (this package, ``teg_regen.py``) and ``sulfur_recovery``
(``sulfur_recovery.py``; built against the U-R reaction contract but NOT yet
registered — see that module's docstring for the measured reason). The
MDEA/MEA/DEA absorbers and regenerators and the TEG contactor keep their
existing modules (``ngdesign.units.mdea_*``, ``teg_contactor``); the TEG-water
equilibrium is owned by ``ngdesign.units.teg_activity`` and is imported, never
re-derived.

Registration is data-driven (``data/unit_models/treating.yaml`` ->
``ngdesign.units.catalogue.register_all``); no ``@register`` decorator here.
"""
