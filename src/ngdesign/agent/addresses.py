"""Variable addresses (spec B-08) - the grammar lives in ``ngdesign.variables``
since P2-01; this module is a re-export so the B-08 tools keep their import path."""

from ngdesign.variables import (  # noqa: F401
    assign as assign,
)
from ngdesign.variables import (
    readable as readable,
)
from ngdesign.variables import (
    resolve as resolve,
)
from ngdesign.variables import (
    set_address as set_address,
)
from ngdesign.variables import (
    writable as writable,
)
