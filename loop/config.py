"""Loop settings. Defaults are OpenRouter and GPT-6 Sol. Keys stay in the environment."""
import json, os, pathlib, shlex, urllib.parse
from dataclasses import dataclass

from loop.errors import LoopBlock

ROOT_KEYS = {"strong_model", "agent", "git", "manuscript", "stop", "usage"}
STRONG_KEYS = {
    "provider", "model", "api_key_env", "base_url", "wire", "extra_headers",
    "timeout_seconds", "key_usage_path", "anthropic_version", "max_tokens",
}
PRESETS = {
    "openrouter": {
        "wire": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "model": "openai/gpt-6-sol",
        "key_usage_path": "key",
        "extra_headers": {"X-Title": "autoresearch-template"},
    },
    "openai": {
        "wire": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "key_usage_path": None,
    },
    "anthropic": {
        "wire": "anthropic",
        "base_url": "https://api.anthropic.com",
        "api_key_env": "ANTHROPIC_API_KEY",
        "key_usage_path": None,
        "anthropic_version": "2023-06-01",
    },
    "gemini": {
        "wire": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "api_key_env": "GEMINI_API_KEY",
        "key_usage_path": None,
    },
    "openai-compatible": {
        "wire": "openai",
        "base_url": None,
        "api_key_env": None,
        "key_usage_path": None,
    },
    "azure": {
        "wire": "azure",
        "base_url": None,
        "api_key_env": "AZURE_API_KEY",
        "key_usage_path": None,
    },
}
DEFAULT_MODEL = "openai/gpt-6-sol"
SECRET_FIELDS = {"api_key", "apikey", "api-key", "authorization", "bearer", "secret", "token"}


def _merge(base, override):
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _reject_inline_secrets(value, where):
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in SECRET_FIELDS:
                raise LoopBlock(
                    f"{where} contains {key}. Put the API key in the environment "
                    f"named by api_key_env, not in the config file."
                )
            _reject_inline_secrets(item, where)
    elif isinstance(value, list):
        for item in value:
            _reject_inline_secrets(item, where)


@dataclass(frozen=True)
class StrongModel:
    provider: str
    model: str
    api_key_env: str
    base_url: str
    wire: str
    extra_headers: tuple
    timeout_seconds: float
    key_usage_path: str | None
    anthropic_version: str
    max_tokens: int | None


@dataclass(frozen=True)
class LoopConfig:
    strong: StrongModel
    agent_argv: tuple
    prompt_via: str
    agent_timeout_minutes: float | None
    git_enabled: bool
    git_remote: str
    paper_rel: str
    response_rel: str
    versions_rel: str
    reviews_rel: str
    progress_rel: str
    state_rel: str
    handoff_rel: str
    ledger_rel: str
    stale_window: int
    max_cycles: int | None


def default_tree():
    return {
        "strong_model": {
            "provider": "openrouter",
            "model": DEFAULT_MODEL,
            "api_key_env": "OPENROUTER_API_KEY",
            "base_url": "https://openrouter.ai/api/v1",
            "wire": "openai",
            "extra_headers": {"X-Title": "autoresearch-template"},
            "timeout_seconds": 900,
            "key_usage_path": "key",
            "anthropic_version": "2023-06-01",
            "max_tokens": None,
        },
        "agent": {"argv": [], "prompt_via": "file", "timeout_minutes": None},
        "git": {"enabled": True, "remote": "origin"},
        "manuscript": {
            "paper": "documents/paper.md",
            "response": "documents/response.md",
            "versions": "documents/versions",
            "reviews": "documents/reviews",
            "progress": "documents/progress",
            "state": "documents/loop-state.json",
            "handoff": "documents/handoff/prompt.md",
        },
        "stop": {"stale_window": 3, "max_cycles": None},
        "usage": {"ledger": "usage/api-usage.jsonl"},
    }


def _explicit_model(file_cfg, env):
    if env.get("AUTORESEARCH_MODEL", "").strip():
        return True
    strong = file_cfg.get("strong_model") or {}
    return "model" in strong


def _load_file(root, env):
    pointed = env.get("AUTORESEARCH_LOOP_CONFIG", "").strip()
    path = pathlib.Path(pointed) if pointed else root / "loop.config.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise LoopBlock(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise LoopBlock(f"{path} must be a JSON object")
    _reject_inline_secrets(data, path.name)
    unknown = set(data) - ROOT_KEYS
    if unknown:
        raise LoopBlock("unknown loop config keys: " + ", ".join(sorted(unknown)))
    strong = data.get("strong_model") or {}
    if not isinstance(strong, dict):
        raise LoopBlock("strong_model must be an object")
    bad = set(strong) - STRONG_KEYS
    if bad:
        raise LoopBlock("unknown strong_model keys: " + ", ".join(sorted(bad)))
    return data


def _as_argv(value):
    if value is None:
        return []
    if isinstance(value, str):
        return shlex.split(value)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    raise LoopBlock("agent.argv must be a list of strings or a command string")


def azure_chat_base(endpoint):
    """Normalize an Azure resource URL to the v1 chat base.

    https://YOUR-RESOURCE.openai.azure.com becomes
    https://YOUR-RESOURCE.openai.azure.com/openai/v1. A URL that already ends
    in /openai/v1 is kept. The deployment name is the model, not part of the URL.
    """
    parts = urllib.parse.urlsplit(endpoint.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise LoopBlock(
            "AZURE_ENDPOINT must be an http(s) URL, such as "
            "https://YOUR-RESOURCE.openai.azure.com."
        )
    path = parts.path.rstrip("/")
    if path.endswith("/chat/completions"):
        path = path[: -len("/chat/completions")].rstrip("/")
    if "/openai/deployments/" in path:
        raise LoopBlock(
            "AZURE_ENDPOINT should be the resource URL, such as "
            "https://YOUR-RESOURCE.openai.azure.com. "
            "Put the deployment name in strong_model.model or AUTORESEARCH_MODEL."
        )
    if path.endswith("/openai/v1"):
        pass
    elif path.endswith("/openai"):
        path = path + "/v1"
    elif path in {"", "/"}:
        path = "/openai/v1"
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, "", "")).rstrip("/")


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise LoopBlock(f"{name} must be a positive integer")
    return value


def _strong_settings(file_cfg, env):
    """Apply the provider preset, then file and environment overrides."""
    file_strong = dict(file_cfg.get("strong_model") or {})
    file_provider = str(file_strong.get("provider") or "openrouter").lower()
    provider = env.get("AUTORESEARCH_PROVIDER", "").strip() or file_provider
    provider = str(provider).lower()
    if provider not in PRESETS:
        raise LoopBlock(
            "unknown provider " + provider
            + ". Use openrouter, openai, anthropic, gemini, azure, or openai-compatible."
        )
    preset = PRESETS[provider]
    strong = dict(default_tree()["strong_model"])
    for key in ("wire", "base_url", "api_key_env", "key_usage_path", "anthropic_version"):
        if key in preset:
            strong[key] = preset[key]
    strong["extra_headers"] = dict(preset.get("extra_headers") or {})
    if provider == "openrouter":
        strong["model"] = preset["model"]
    # Connection fields in the file belong to file_provider. A provider switch
    # keeps model, timeout, and max_tokens, and takes the new preset's URL and key.
    carried = file_strong if file_provider == provider else {
        key: file_strong[key] for key in ("model", "max_tokens", "timeout_seconds") if key in file_strong
    }
    for key, value in carried.items():
        if key != "provider":
            strong[key] = value
    if env.get("AUTORESEARCH_MODEL", "").strip():
        strong["model"] = env["AUTORESEARCH_MODEL"].strip()
    if env.get("AUTORESEARCH_BASE_URL", "").strip():
        strong["base_url"] = env["AUTORESEARCH_BASE_URL"].strip()
    if env.get("AUTORESEARCH_API_KEY_ENV", "").strip():
        strong["api_key_env"] = env["AUTORESEARCH_API_KEY_ENV"].strip()
    if provider != "openrouter" and not _explicit_model(file_cfg, env):
        raise LoopBlock(
            f"provider {provider} needs its own model. "
            f"The default {DEFAULT_MODEL} is the OpenRouter slug for GPT-6 Sol. "
            "Set strong_model.model or AUTORESEARCH_MODEL."
        )
    if (
        provider in {"anthropic", "gemini", "azure"}
        and strong.get("model") == DEFAULT_MODEL
        and not env.get("AUTORESEARCH_MODEL", "").strip()
    ):
        raise LoopBlock(
            f"{DEFAULT_MODEL} is the OpenRouter slug for GPT-6 Sol. "
            f"Set strong_model.model or AUTORESEARCH_MODEL for provider {provider}."
        )
    if provider == "azure":
        endpoint = str(strong.get("base_url") or "").strip() or env.get("AZURE_ENDPOINT", "").strip()
        if not endpoint:
            raise LoopBlock(
                "Set AZURE_ENDPOINT to the Azure resource URL, such as "
                "https://YOUR-RESOURCE.openai.azure.com. "
                "The key is read from AZURE_API_KEY."
            )
        strong["base_url"] = azure_chat_base(endpoint)
    if strong.get("wire") not in {"openai", "anthropic", "gemini", "azure"}:
        raise LoopBlock("wire must be openai, anthropic, gemini, or azure")
    return provider, strong


def load_config(root, env=None):
    """Resolve defaults, the optional config file, and environment overrides."""
    env = os.environ if env is None else env
    root = pathlib.Path(root)
    file_cfg = _load_file(root, env)
    provider, strong = _strong_settings(file_cfg, env)
    merged = _merge(default_tree(), file_cfg)
    merged["strong_model"] = strong
    strong["provider"] = provider
    if not strong.get("base_url") or not str(strong["base_url"]).startswith(("https://", "http://")):
        raise LoopBlock("strong_model.base_url must be an http(s) URL")
    if not strong.get("model") or not str(strong["model"]).strip():
        raise LoopBlock("strong_model.model is required")
    if not strong.get("api_key_env"):
        raise LoopBlock("strong_model.api_key_env is required")
    headers = strong.get("extra_headers") or {}
    if not isinstance(headers, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
        raise LoopBlock("extra_headers must be an object of strings")
    timeout = strong.get("timeout_seconds", 900)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise LoopBlock("timeout_seconds must be a positive number")
    max_tokens = strong.get("max_tokens")
    if max_tokens is not None:
        max_tokens = _positive_int(max_tokens, "max_tokens")
    agent = merged["agent"]
    command = env.get("AUTORESEARCH_AGENT_COMMAND", "").strip()
    argv = _as_argv(command) if command else _as_argv(agent.get("argv"))
    prompt_via = env.get("AUTORESEARCH_PROMPT_VIA", "").strip() or agent.get("prompt_via") or "file"
    if prompt_via not in {"file", "argv", "stdin"}:
        raise LoopBlock("prompt_via must be file, argv, or stdin")
    timeout_minutes = agent.get("timeout_minutes")
    if timeout_minutes is not None:
        if isinstance(timeout_minutes, bool) or not isinstance(timeout_minutes, (int, float)) or timeout_minutes <= 0:
            raise LoopBlock("agent.timeout_minutes must be a positive number")
    stop = merged["stop"]
    window = _positive_int(stop.get("stale_window", 3), "stop.stale_window")
    max_cycles = stop.get("max_cycles")
    if max_cycles is not None:
        max_cycles = _positive_int(max_cycles, "stop.max_cycles")
    docs = merged["manuscript"]
    usage = merged["usage"]
    key_path = strong.get("key_usage_path")
    if key_path is not None:
        key_path = str(key_path)
    return LoopConfig(
        strong=StrongModel(
            provider=provider,
            model=str(strong["model"]),
            api_key_env=str(strong["api_key_env"]),
            base_url=str(strong["base_url"]).rstrip("/"),
            wire=strong["wire"],
            extra_headers=tuple(sorted(headers.items())),
            timeout_seconds=float(timeout),
            key_usage_path=key_path,
            anthropic_version=str(strong.get("anthropic_version") or "2023-06-01"),
            max_tokens=max_tokens,
        ),
        agent_argv=tuple(argv),
        prompt_via=prompt_via,
        agent_timeout_minutes=None if timeout_minutes is None else float(timeout_minutes),
        git_enabled=bool(merged["git"].get("enabled", True)),
        git_remote=str(merged["git"].get("remote") or "origin"),
        paper_rel=str(docs["paper"]),
        response_rel=str(docs["response"]),
        versions_rel=str(docs["versions"]),
        reviews_rel=str(docs["reviews"]),
        progress_rel=str(docs["progress"]),
        state_rel=str(docs["state"]),
        handoff_rel=str(docs["handoff"]),
        ledger_rel=str(usage["ledger"]),
        stale_window=window,
        max_cycles=max_cycles,
    )


def require_api_key(cfg, env=None):
    env = os.environ if env is None else env
    direct = env.get("AUTORESEARCH_API_KEY", "").strip()
    if direct:
        return direct, "AUTORESEARCH_API_KEY"
    name = cfg.strong.api_key_env
    value = env.get(name, "").strip()
    if not value:
        raise LoopBlock(
            f"Set {name} for provider {cfg.strong.provider}. "
            "The key stays in the environment. It is not written to loop.config.json or the usage ledger."
        )
    return value, name


def require_agent(cfg):
    argv = list(cfg.agent_argv)
    if not argv:
        raise LoopBlock(
            "No research agent command is configured. Set agent.argv in loop.config.json "
            "or AUTORESEARCH_AGENT_COMMAND. Example: "
            "export AUTORESEARCH_AGENT_COMMAND='your-agent --prompt-file {prompt_file}'. "
            "The command runs once per manuscript version and exits when documents/paper.md is ready. "
            "This template does not assume a cluster or a particular agent."
        )
    joined = " ".join(argv)
    if cfg.prompt_via == "file" and "{prompt_file}" not in joined:
        raise LoopBlock("agent command must include {prompt_file}, or set prompt_via to stdin or argv.")
    if cfg.prompt_via == "argv" and "{prompt}" not in joined and "{prompt_file}" not in joined:
        raise LoopBlock("prompt_via argv requires {prompt} or {prompt_file} in the command.")
    return argv
