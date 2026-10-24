"""Profile one Preflash example solve (U-H1 re-review item 2).

Mirrors tests/property/test_unit_balances.py: thermo = registry "pr",
inlets = flash_feed(thermo, feed).
"""

import cProfile
import io
import pstats
import time

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.refining.preflash import Preflash


def main() -> None:
    names = registry.available("thermo")
    thermo: Thermo = registry.create("thermo", "pr" if "pr" in names else names[0])

    feeds, params = Preflash.example_case()
    inlets = {
        port: thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"])
        for port, f in feeds.items()
    }

    # the feed flash alone, timed (review reference: 0.8 s)
    t0 = time.perf_counter()
    thermo.flash_pt(feeds["feed_in"]["composition"], feeds["feed_in"]["T"], feeds["feed_in"]["P"], feeds["feed_in"]["molar_flow"])
    t1 = time.perf_counter()
    print(f"feed flash_pt alone: {t1 - t0:.2f} s", flush=True)

    prof = cProfile.Profile()
    t0 = time.perf_counter()
    prof.enable()
    Preflash().solve(inlets, params, thermo)
    prof.disable()
    t1 = time.perf_counter()
    print(f"full solve: {t1 - t0:.2f} s", flush=True)

    out = io.StringIO()
    stats = pstats.Stats(prof, stream=out)
    stats.sort_stats("cumulative").print_stats(30)
    stats.sort_stats("tottime").print_stats(15)
    print(out.getvalue(), flush=True)


if __name__ == "__main__":
    main()
