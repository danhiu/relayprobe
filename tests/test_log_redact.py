from app.detector.log_redact import redact


def test_redact_sk_key():
    assert redact("Bearer sk-abcdef1234567890") == "Bearer sk-abc***90"


def test_redact_short_sk_key_fully_masked():
    assert redact("sk-abc") == "sk-***"


def test_redact_multiple_keys_in_string():
    text = "key1=sk-AAAAAAAAAA and key2=sk-BBBBBBBBBB"
    out = redact(text)
    assert "sk-AAA***AA" in out
    assert "sk-BBB***BB" in out


def test_redact_no_key():
    assert redact("hello world") == "hello world"


def test_redact_handles_none_safely():
    assert redact(None) is None
