"""Strong-model calls. OpenAI-compatible, Anthropic, and Gemini wires."""
import json
from urllib import error, request

from loop.errors import ProviderError
from loop.secrets import redact_text


def _join(base, path):
    return base.rstrip("/") + "/" + path.lstrip("/")


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def urllib_transport(method, url, headers, body, timeout):
    opener = request.build_opener(_NoRedirect)
    payload = None if body is None else body
    req = request.Request(url, data=payload, headers=headers, method=method)
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers.items()), resp.read()
    except error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()


def _message_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
        if parts:
            return "".join(parts)
    raise ProviderError("model returned no text")


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


class Completion:
    def __init__(self, text, prompt_tokens, completion_tokens, total_tokens, cost_usd, request_id):
        self.text = text
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens
        self.cost_usd = cost_usd
        self.request_id = request_id


class Provider:
    def __init__(self, cfg, api_key, transport=None):
        self.cfg = cfg.strong
        self._key = api_key
        self._transport = transport or urllib_transport

    def __repr__(self):
        return f"Provider(provider={self.cfg.provider!r}, model={self.cfg.model!r})"

    def complete(self, messages):
        if self.cfg.wire == "anthropic":
            return self._anthropic(messages)
        if self.cfg.wire == "gemini":
            return self._gemini(messages)
        return self._openai(messages)

    def key_usage(self):
        if not self.cfg.key_usage_path:
            return None
        status, raw = self._send("GET", _join(self.cfg.base_url, self.cfg.key_usage_path), None)
        if not isinstance(raw, dict):
            raise ProviderError("key usage response was not a JSON object", status=status)
        return raw

    def _headers(self, extra):
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        headers.update(dict(self.cfg.extra_headers))
        headers.update(extra)
        return headers

    def _send(self, method, url, payload):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        try:
            status, _headers, raw = self._transport(
                method, url, self._auth_headers(), body, self.cfg.timeout_seconds
            )
        except Exception as exc:
            raise ProviderError(redact_text(f"{self.cfg.provider} request failed: {exc}", self._key)) from exc
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        if status >= 400:
            raise ProviderError(
                redact_text(f"{self.cfg.provider} HTTP {status}", self._key),
                status=status,
            )
        try:
            parsed = json.loads(text) if text else {}
        except json.JSONDecodeError as exc:
            raise ProviderError(f"{self.cfg.provider} returned non-JSON", status=status) from exc
        return status, parsed

    def _auth_headers(self):
        if self.cfg.wire == "anthropic":
            return self._headers({
                "x-api-key": self._key,
                "anthropic-version": self.cfg.anthropic_version,
            })
        if self.cfg.wire == "gemini":
            return self._headers({"x-goog-api-key": self._key})
        if self.cfg.wire == "azure":
            return self._headers({"api-key": self._key})
        return self._headers({"Authorization": "Bearer " + self._key})

    def _usage_from(self, usage):
        usage = usage or {}
        prompt = _number(usage.get("prompt_tokens", usage.get("input_tokens")))
        completion = _number(usage.get("completion_tokens", usage.get("output_tokens")))
        total = _number(usage.get("total_tokens"))
        if total is None and prompt is not None and completion is not None:
            total = prompt + completion
        cost = _number(usage.get("cost", usage.get("cost_usd", usage.get("total_cost"))))
        return prompt, completion, total, cost

    def _openai(self, messages):
        payload = {"model": self.cfg.model, "messages": messages}
        if self.cfg.max_tokens is not None:
            payload["max_tokens"] = self.cfg.max_tokens
        _status, body = self._send("POST", _join(self.cfg.base_url, "chat/completions"), payload)
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("OpenAI-compatible response had no message") from exc
        prompt, completion, total, cost = self._usage_from(body.get("usage"))
        return Completion(_message_text(content), prompt, completion, total, cost, body.get("id"))

    def _anthropic(self, messages):
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        convo = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
        payload = {
            "model": self.cfg.model,
            "max_tokens": self.cfg.max_tokens or 16000,
            "messages": convo,
        }
        if system:
            payload["system"] = system
        _status, body = self._send("POST", _join(self.cfg.base_url, "v1/messages"), payload)
        parts = body.get("content") or []
        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
        if not text:
            raise ProviderError("Anthropic response had no text")
        prompt, completion, total, cost = self._usage_from(body.get("usage"))
        return Completion(text, prompt, completion, total, cost, body.get("id"))

    def _gemini(self, messages):
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = []
        for message in messages:
            if message["role"] == "system":
                continue
            role = "model" if message["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": message["content"]}]})
        payload = {"contents": contents}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if self.cfg.max_tokens is not None:
            payload["generationConfig"] = {"maxOutputTokens": self.cfg.max_tokens}
        model = self.cfg.model.replace("/", "%2F")
        url = _join(self.cfg.base_url, f"models/{model}:generateContent")
        _status, body = self._send("POST", url, payload)
        try:
            parts = body["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Gemini response had no text") from exc
        meta = body.get("usageMetadata") or {}
        prompt = _number(meta.get("promptTokenCount"))
        completion = _number(meta.get("candidatesTokenCount"))
        total = _number(meta.get("totalTokenCount"))
        return Completion(text, prompt, completion, total, None, None)
