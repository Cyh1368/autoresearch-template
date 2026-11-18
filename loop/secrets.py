"""Redaction helpers. Raw API keys never belong in ledgers, errors, or git."""
import re

_KEY = re.compile(
    r"(sk-or-v1-[A-Za-z0-9]{12,}"
    r"|sk-ant-[A-Za-z0-9_\-]{12,}"
    r"|sk-proj-[A-Za-z0-9_\-]{12,}"
    r"|sk-[A-Za-z0-9]{20,}"
    r"|AIza[0-9A-Za-z_\-]{20,}"
    r"|ghp_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|xai-[A-Za-z0-9]{20,})"
)


def key_hint(env_name, secret):
    if not secret:
        return f"{env_name} (not set)"
    tail = secret[-4:] if len(secret) >= 4 else "****"
    return f"{env_name} ...{tail}"


def redact_text(text, secret=None):
    if text is None:
        return ""
    out = str(text)
    if secret:
        out = out.replace(secret, "***")
    return _KEY.sub("***", out)


def redact_obj(value, secret=None):
    if isinstance(value, dict):
        return {str(k): redact_obj(v, secret) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_obj(v, secret) for v in value]
    if isinstance(value, str):
        return redact_text(value, secret)
    return value
