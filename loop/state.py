"""Atomic review state for submit. Separate from the campaign policy and ledger."""
import json, os, pathlib


def empty_state():
    return {
        "brief_sha256": None,
        "status": "running",
        "reason": "",
        "versions": [],
    }


def load_state(root, cfg):
    path = pathlib.Path(root) / cfg.state_rel
    if not path.is_file():
        return empty_state()
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("brief_sha256", None)
    data.setdefault("status", "running")
    data.setdefault("reason", "")
    data.setdefault("versions", [])
    return data


def save_state(root, cfg, state):
    path = pathlib.Path(root) / cfg.state_rel
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
