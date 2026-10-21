"""Variable addresses (spec B-08) - the grammar lives in ``ngdesign.variables``
since P2-01; this module is a re-export so the B-08 tools keep their import path."""

from ngdesign.variables import assign, readable, resolve, set_address, writable

__all__ = ["assign", "readable", "resolve", "set_address", "writable"]
