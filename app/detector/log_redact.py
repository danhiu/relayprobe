"""Mask API keys in log output. Used by both the logging filter and ad-hoc string masking."""
import logging
import re

# Match sk-XXXXXX style keys (Anthropic, OpenAI, generic relay keys all use this prefix family)
_SK_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]+")


def _mask(match: re.Match) -> str:
    raw = match.group(0)
    # raw looks like "sk-XXXX..."
    body = raw[3:]
    if len(body) <= 5:
        return "sk-***"
    return f"sk-{body[:3]}***{body[-2:]}"


def redact(value):
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    return _SK_PATTERN.sub(_mask, value)


class RedactFilter(logging.Filter):
    """Logging filter that masks API keys in record messages and args."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            record.args = tuple(
                redact(a) if isinstance(a, str) else a for a in record.args
            )
        return True


def install_global_filter() -> None:
    """Attach RedactFilter to the root logger so every emitter goes through it."""
    root = logging.getLogger()
    if not any(isinstance(f, RedactFilter) for f in root.filters):
        root.addFilter(RedactFilter())
