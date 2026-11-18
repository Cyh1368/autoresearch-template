"""Local API-usage ledger and the human-readable report."""
import datetime, fcntl, json, pathlib

from loop.secrets import key_hint, redact_obj, redact_text


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def append_usage(root, cfg, record):
    path = pathlib.Path(root) / cfg.ledger_rel
    path.parent.mkdir(parents=True, exist_ok=True)
    row = dict(record)
    row.setdefault("time", _now())
    line = json.dumps(row, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.write(line)
        handle.flush()
    return row


def read_usage(root, cfg):
    path = pathlib.Path(root) / cfg.ledger_rel
    if not path.is_file():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_SH)
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _money(value):
    if value is None:
        return "n/a"
    return f"${float(value):.6f}".rstrip("0").rstrip(".")


def _add(bucket, row):
    bucket["calls"] += 1
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = row.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            bucket[key] += value
    cost = row.get("cost_usd")
    if isinstance(cost, (int, float)) and not isinstance(cost, bool):
        bucket["cost"] += float(cost)
        bucket["cost_known"] = True


def format_report(cfg, rows, *, key_name, secret, live=None, live_note=None):
    lines = [
        "Strong model",
        f"  provider: {cfg.strong.provider}",
        f"  model: {cfg.strong.model}",
        f"  base URL: {cfg.strong.base_url}",
        f"  key: {key_hint(key_name, secret)}",
        "",
        f"Local ledger ({cfg.ledger_rel})",
    ]
    if not rows:
        lines.append("  no calls recorded yet")
    else:
        totals = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost": 0.0, "cost_known": False}
        by_op = {}
        for row in rows:
            _add(totals, row)
            op = row.get("operation") or "call"
            by_op.setdefault(op, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost": 0.0, "cost_known": False})
            _add(by_op[op], row)
        lines.append(f"  calls: {totals['calls']}")
        lines.append(
            "  tokens: "
            f"{int(totals['prompt_tokens'])} prompt, "
            f"{int(totals['completion_tokens'])} completion, "
            f"{int(totals['total_tokens'])} total"
        )
        lines.append("  reported cost: " + (_money(totals["cost"]) if totals["cost_known"] else "n/a"))
        for op in sorted(by_op):
            item = by_op[op]
            cost = _money(item["cost"]) if item["cost_known"] else "n/a"
            lines.append(
                f"  {op}: {item['calls']} calls, "
                f"{int(item['prompt_tokens'])} prompt, "
                f"{int(item['completion_tokens'])} completion, "
                f"cost {cost}"
            )
        lines.append("")
        lines.append("Recent calls")
        for row in rows[-10:]:
            lines.append(
                "  "
                f"{row.get('time', '')}  {row.get('operation', '')}  "
                f"v{row.get('version', '-') }  "
                f"prompt {row.get('prompt_tokens')}  "
                f"completion {row.get('completion_tokens')}  "
                f"cost {_money(row.get('cost_usd'))}  "
                f"{row.get('status', '')}"
            )
    lines.append("")
    if live_note:
        lines.append(live_note)
    elif live is not None:
        lines.append("Live key usage")
        lines.extend(_format_live(cfg.strong.provider, live, secret))
    text = "\n".join(lines) + "\n"
    return redact_text(text, secret)


def _format_live(provider, payload, secret):
    data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else payload
    if provider == "openrouter" and isinstance(data, dict):
        lines = []
        label = data.get("label")
        if label:
            lines.append(f"  label: {label}")
        for name in ("usage", "usage_daily", "usage_weekly", "usage_monthly"):
            if name in data:
                lines.append(f"  {name} USD: {data[name]}")
        if "limit" in data or "limit_remaining" in data:
            lines.append(
                "  limit USD: "
                f"{data.get('limit')} remaining {data.get('limit_remaining')} "
                f"reset {data.get('limit_reset')}"
            )
        for name in ("byok_usage", "byok_usage_daily", "byok_usage_weekly", "byok_usage_monthly"):
            if name in data:
                lines.append(f"  {name} USD: {data[name]}")
        budget = data.get("effective_budget")
        if isinstance(budget, dict):
            lines.append(
                "  effective budget USD: "
                f"spend {budget.get('spend_usd')} remaining {budget.get('remaining_usd')} "
                f"limit {budget.get('limit_usd')} reset {budget.get('reset_interval')}"
            )
        if data.get("is_free_tier") is not None:
            lines.append(f"  free tier: {data.get('is_free_tier')}")
        return [redact_text(line, secret) for line in lines]
    redacted = redact_obj(payload, secret)
    return ["  " + line for line in json.dumps(redacted, indent=2).splitlines()]
