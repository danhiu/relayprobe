import re

from app.detector.probes import draw, load_probes


def test_load_probes_returns_categories():
    probes = load_probes()
    assert "identity" in probes
    assert "tool_use" in probes
    assert "sub_agent_user_prompt" in probes
    assert len(probes["identity"]) >= 5


def test_draw_appends_nonce():
    prompt, nonce = draw("identity")
    assert nonce in prompt
    assert re.match(r"REQ-[a-f0-9]{8}", nonce)


def test_draw_returns_distinct_nonces():
    _, n1 = draw("identity")
    _, n2 = draw("identity")
    assert n1 != n2


def test_draw_unknown_category_raises():
    import pytest

    with pytest.raises(KeyError):
        draw("no_such_category")
