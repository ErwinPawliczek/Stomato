"""Thermo-model selection on the flowsheet contract (expansion spec, foundation PR).

The field defaults to "pr" and carries a registered "thermo" plugin name;
resolution happens at solve entry (registry seam), so an unknown name fails the
solve there — the HTTP surface is covered in tests/api/test_solve.py.
"""

from ngdesign.contracts import DEFAULT_SLATE, Flowsheet
from ngdesign.data import components
from ngdesign.flowsheets import slice as slice_fs


def test_thermo_defaults_to_pr() -> None:
    assert slice_fs.build().thermo == "pr"
    assert Flowsheet(name="x", units=[], streams=[]).thermo == "pr"


def test_thermo_selection_round_trips() -> None:
    fs = Flowsheet(name="x", units=[], streams=[], thermo="srk")
    assert fs.thermo == "srk"


def test_new_components_databanked() -> None:
    """MeOH and MEG joined the slate through the data/components.yaml generation path."""
    table = components()
    for cid in ("MeOH", "MEG"):
        assert cid in DEFAULT_SLATE
        assert {"name", "cas", "mw", "tc_K", "pc_Pa", "omega"} <= set(table[cid])


def test_amine_components_databanked() -> None:
    """CO2 and H2S stay in the tuple: the amine units flash them through pr.py."""
    assert {"CO2", "H2S"} <= set(DEFAULT_SLATE)
    assert {"CO2", "H2S"} <= set(components())
