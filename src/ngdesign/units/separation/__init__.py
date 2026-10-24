"""Separation-family R0 adapters (spec U-D, plan §2 U-D).

One module per unit; registration comes from the catalogue YAML
(``data/unit_models/separation.yaml``) via ``units.catalogue.register_all`` —
no ``@register`` decorator here (round-1 conventions). R0 means balances plus
a spec: every unit here flashes with the ``Thermo`` protocol and reports the
balancing duty; no sizing physics.
"""
