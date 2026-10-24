"""Refining-family unit adapters (spec U-H2).

Reactor rows implemented as mass-only yield-table units: `reactors_coker`,
`reactors_reformer` and `reactors_hdt`. Each module registers its pseudo
lumps at import (the catalogue loader imports adapters by
``module:ClassName`` string, so registration is definitional data, not
plugin state).
"""
