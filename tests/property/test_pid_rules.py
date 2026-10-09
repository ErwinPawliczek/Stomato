"""Every P&ID rule: apply() then check() must report nothing, and apply is idempotent. LOCKED."""

import pytest

from ngdesign import registry
from ngdesign.flowsheets.samples import sample_pid

RULES = registry.available("pid_rule")


@pytest.mark.parametrize("name", RULES or ["<none>"])
def test_rule_apply_then_check_clean(name):
    if name == "<none>":
        pytest.skip("no pid rules yet")
    rule = registry.create("pid_rule", name)
    raw = sample_pid()
    assert rule.check(raw), f"{name}: rule finds nothing on the bare sample; it is not testing anything"
    fixed = rule.apply(raw)
    assert rule.check(fixed) == []
    assert rule.apply(fixed).model_dump() == fixed.model_dump(), f"{name}: apply is not idempotent"


def test_all_rules_compose():
    """Rules can create work for each other (a new PSV line needs isolation), so apply to a fixed point."""
    if not RULES:
        pytest.skip("no pid rules yet")
    pid = sample_pid()
    for _ in range(5):
        before = pid.model_dump()
        for name in RULES:
            pid = registry.create("pid_rule", name).apply(pid)
        if pid.model_dump() == before:
            break
    else:
        pytest.fail("rules did not reach a fixed point in 5 passes")
    for name in RULES:
        assert registry.create("pid_rule", name).check(pid) == [], f"{name} broken by another rule"
