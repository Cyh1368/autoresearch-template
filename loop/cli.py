"""Commands: loop, usage, review."""
import argparse, pathlib

from loop.config import load_config, require_api_key
from loop.errors import LoopBlock, ProviderError
from loop.orchestrator import run_loop, run_review_once
from loop.provider import Provider
from loop.usage import format_report, read_usage

_EXIT = {"accepted": 0, "stalled": 3, "blocked": 2, "running": 0}


def usage_report(root, *, live, env=None, transport=None):
    cfg = load_config(root, env)
    rows = read_usage(root, cfg)
    secret = ""
    key_name = cfg.strong.api_key_env
    live_payload = None
    live_note = None
    if not live:
        try:
            secret, key_name = require_api_key(cfg, env)
        except LoopBlock:
            secret = ""
    elif not cfg.strong.key_usage_path:
        live_note = (
            f"{cfg.strong.provider} does not expose a key-usage endpoint. "
            "Showing the local ledger."
        )
        try:
            secret, key_name = require_api_key(cfg, env)
        except LoopBlock:
            secret = ""
    else:
        try:
            secret, key_name = require_api_key(cfg, env)
            live_payload = Provider(cfg, secret, transport=transport).key_usage()
        except (LoopBlock, ProviderError) as exc:
            live_note = f"Live key usage unavailable: {exc}"
    return format_report(
        cfg, rows, key_name=key_name, secret=secret, live=live_payload, live_note=live_note,
    )


def main(argv, root=None, env=None, transport=None):
    parser = argparse.ArgumentParser(prog="bin/autoresearch")
    sub = parser.add_subparsers(dest="command", required=True)
    loop = sub.add_parser("loop", help="run agent versions, strong-model review, and git sync")
    loop.add_argument("--max-cycles", type=int, default=None)
    usage = sub.add_parser("usage", help="show strong-model token spend and live key usage")
    usage.add_argument("--live", action=argparse.BooleanOptionalAction, default=True)
    sub.add_parser("review", help="send the current manuscript to the strong model once")
    args = parser.parse_args(list(argv))
    root = pathlib.Path(root) if root is not None else pathlib.Path(__file__).resolve().parents[1]
    if args.command == "loop":
        result = run_loop(root, env=env, transport=transport, max_cycles=args.max_cycles)
        print(f"{result['status']}: {result['reason']}")
        return _EXIT[result["status"]]
    if args.command == "usage":
        print(usage_report(root, live=args.live, env=env, transport=transport), end="")
        return 0
    run_review_once(root, env=env, transport=transport)
    return 0
