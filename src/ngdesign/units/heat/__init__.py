"""U-C heat-transfer R0 units (spec U-C, conventions U-R1).

One adapter module per unit or unit pair; registration comes from the
catalogue rows in ``data/unit_models/heat.yaml`` (no ``@register`` decorators
here - ``units.catalogue.register_all`` imports and registers these classes
from the YAML adapter strings).
"""
