"""One manuscript version per research-agent process, then a strong-model review."""
import fcntl, hashlib, json, pathlib, subprocess

from loop import manuscript as papers
from loop.config import load_config, require_agent, require_api_key
from loop.errors import GitError, LoopBlock, ProviderError
from loop.git_sync import GitSync
from loop.parse import parse_decision, parse_json_object, parse_progress
from loop.provider import Provider
from loop.secrets import key_hint
from loop.state import load_state, save_state
from loop.usage import append_usage


def _brief_sha(root):
    path = pathlib.Path(root) / "RESEARCH_BRIEF.md"
    if not path.is_file():
        raise LoopBlock("RESEARCH_BRIEF.md is missing.")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_brief(root, cfg, state):
    digest = _brief_sha(root)
    if state.get("brief_sha256") is None:
        state["brief_sha256"] = digest
        save_state(root, cfg, state)
        return
    if state["brief_sha256"] != digest:
        raise LoopBlock(
            "RESEARCH_BRIEF.md changed after the loop started. "
            "Keep this loop state and create a new one if the brief should change."
        )


def _previous_response_sha(state):
    for item in reversed(state["versions"]):
        if item.get("response_sent") and item.get("response_sha256"):
            return item["response_sha256"]
    return None


def _record(root, cfg, *, operation, version, provider, secret, key_name, status, completion=None, error=None):
    strong = provider.cfg
    row = {
        "operation": operation,
        "version": version,
        "provider": strong.provider,
        "model": strong.model,
        "base_url": strong.base_url,
        "key": key_hint(key_name, secret),
        "status": status,
        "error": error,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "cost_usd": None,
        "request_id": None,
    }
    if completion is not None:
        row.update({
            "prompt_tokens": completion.prompt_tokens,
            "completion_tokens": completion.completion_tokens,
            "total_tokens": completion.total_tokens,
            "cost_usd": completion.cost_usd,
            "request_id": completion.request_id,
        })
    stored = append_usage(root, cfg, row)
    cost = "n/a" if stored["cost_usd"] is None else stored["cost_usd"]
    print(
        f"{operation} version {version}: status {status} "
        f"prompt {stored['prompt_tokens']} completion {stored['completion_tokens']} "
        f"cost {cost} key {stored['key']}"
    )
    return stored


def _complete_json(root, cfg, provider, messages, parser, *, operation, version, secret, key_name):
    conversation = list(messages)
    last_error = "no attempt"
    for attempt in range(2):
        try:
            completion = provider.complete(conversation)
        except ProviderError as exc:
            _record(
                root, cfg, operation=operation, version=version, provider=provider,
                secret=secret, key_name=key_name, status="error", error=str(exc),
            )
            if exc.status in {400, 401, 403, 404} or attempt == 1:
                raise LoopBlock(str(exc)) from exc
            last_error = str(exc)
            continue
        _record(
            root, cfg, operation=operation, version=version, provider=provider,
            secret=secret, key_name=key_name, status="ok", completion=completion,
        )
        try:
            return parser(parse_json_object(completion.text))
        except ValueError as exc:
            last_error = str(exc)
            conversation = conversation + [
                {"role": "assistant", "content": completion.text[:8000]},
                {"role": "user", "content": "Reply with one JSON object only, matching the schema you were given."},
            ]
    raise LoopBlock(f"{operation} reply was not usable: {last_error}")


def _publish_named_review(root, result, text):
    documents = pathlib.Path(root) / "documents"
    documents.mkdir(parents=True, exist_ok=True)
    remark = documents / "REMARK.md"
    critique = documents / "REVIEW.md"
    if result["decision"] == "accept":
        remark.write_text(text, encoding="utf-8")
        if critique.exists():
            critique.unlink()
    else:
        critique.write_text(text, encoding="utf-8")
        if remark.exists():
            remark.unlink()


def _write_review(root, cfg, number, result):
    folder = pathlib.Path(root) / cfg.reviews_rel
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"v{number:03d}.md"
    body = result["review_markdown"]
    if result.get("summary"):
        body = result["summary"] + "\n\n" + body
    text = body.rstrip() + "\n"
    path.write_text(text, encoding="utf-8")
    _publish_named_review(root, result, text)
    meta = folder / f"v{number:03d}.json"
    meta.write_text(
        json.dumps(
            {"version": number, "decision": result["decision"], "summary": result.get("summary", "")},
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return path


def _apply_decision(state, number, result):
    state["versions"][-1]["decision"] = result["decision"]
    if result["decision"] == "accept":
        state["status"] = "accepted"
        state["reason"] = f"accepted at version {number}"
    else:
        state["status"] = "running"
        state["reason"] = f"revise at version {number}"


def _review_version(root, cfg, state, provider, secret, key_name, manuscript, response_text, note):
    number = len(state["versions"]) + 1
    papers.snapshot(root, cfg, number, manuscript, response_text, note)
    state["versions"].append({
        "n": number,
        "paper_sha256": manuscript.paper_sha256,
        "response_sha256": manuscript.response_sha256 if response_text is not None else None,
        "response_sent": response_text is not None,
        "decision": None,
        "progress": None,
    })
    save_state(root, cfg, state)
    print(f"Calling {cfg.strong.provider} model {cfg.strong.model} for review of version {number}.")
    result = _complete_json(
        root, cfg, provider,
        [
            {"role": "system", "content": papers.load_prompt("review.md")},
            {"role": "user", "content": papers.review_user_message(manuscript, response_text, note)},
        ],
        parse_decision,
        operation="review", version=number, secret=secret, key_name=key_name,
    )
    path = _write_review(root, cfg, number, result)
    _apply_decision(state, number, result)
    save_state(root, cfg, state)
    print(f"Review of version {number}: {result['decision']} ({path})")
    return result


def _finish_open_review(root, cfg, state, provider, secret, key_name):
    """Review a snapshot that was saved before an earlier call failed."""
    item = state["versions"][-1]
    number = item["n"]
    folder = papers.version_dir(root, cfg, number)
    paper = (folder / "paper.md").read_text(encoding="utf-8")

    class _Snap:
        pass

    snap = _Snap()
    snap.paper = paper
    response_text = None
    note = "No author response was sent for this version."
    if item.get("response_sent"):
        response_text = (folder / "response.md").read_text(encoding="utf-8")
        note = None
    print(f"Calling {cfg.strong.provider} model {cfg.strong.model} for review of version {number}.")
    result = _complete_json(
        root, cfg, provider,
        [
            {"role": "system", "content": papers.load_prompt("review.md")},
            {"role": "user", "content": papers.review_user_message(snap, response_text, note)},
        ],
        parse_decision,
        operation="review", version=number, secret=secret, key_name=key_name,
    )
    path = _write_review(root, cfg, number, result)
    _apply_decision(state, number, result)
    save_state(root, cfg, state)
    print(f"Review of version {number}: {result['decision']} ({path})")
    return result


def _progress_check(root, cfg, state, provider, secret, key_name):
    window = state["versions"][-cfg.stale_window:]
    numbers = [item["n"] for item in window]
    print(
        f"Calling {cfg.strong.provider} model {cfg.strong.model} "
        f"for progress across versions {numbers[0]}-{numbers[-1]}."
    )
    result = _complete_json(
        root, cfg, provider,
        [
            {"role": "system", "content": papers.load_prompt("progress.md")},
            {"role": "user", "content": papers.progress_user_message(root, cfg, window)},
        ],
        parse_progress,
        operation="progress", version=numbers[-1], secret=secret, key_name=key_name,
    )
    state["versions"][-1]["progress"] = result
    folder = pathlib.Path(root) / cfg.progress_rel
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"v{numbers[-1]:03d}.json").write_text(
        json.dumps({"versions": numbers, **result}, indent=2) + "\n",
        encoding="utf-8",
    )
    if not result["significant_progress"]:
        state["status"] = "stalled"
        state["reason"] = (
            f"no significant progress across versions {numbers[0]}-{numbers[-1]}: "
            + result["rationale"]
        )
    else:
        state["status"] = "running"
        state["reason"] = f"progress across versions {numbers[0]}-{numbers[-1]}"
    save_state(root, cfg, state)
    print(state["reason"])
    return result


def _needs_progress(cfg, state):
    if len(state["versions"]) < cfg.stale_window:
        return False
    last = state["versions"][-1]
    return last.get("decision") == "revise" and last.get("progress") is None


def _scientific_stop(cfg, state):
    if not state["versions"]:
        return None
    last = state["versions"][-1]
    if last.get("decision") == "accept":
        return "accepted", f"accepted at version {last['n']}"
    progress = last.get("progress") or {}
    if progress.get("significant_progress") is False:
        window = state["versions"][-cfg.stale_window:]
        span = f"{window[0]['n']}-{window[-1]['n']}"
        rationale = progress.get("rationale") or "the strong model reported no significant progress"
        return "stalled", f"no significant progress across versions {span}: {rationale}"
    return None


def _unreviewed(state, manuscript):
    if manuscript is None:
        return False
    if not state["versions"]:
        return True
    last = state["versions"][-1]
    if last.get("decision") is None:
        return False
    return manuscript.paper_sha256 != last.get("paper_sha256")


class _Lock:
    def __init__(self, root):
        folder = pathlib.Path(root) / "documents"
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / ".loop.lock"
        self.handle = None

    def __enter__(self):
        self.handle = self.path.open("a+")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LoopBlock("Another autoresearch loop is already running in this repository.") from exc
        return self

    def __exit__(self, *_args):
        if self.handle is not None:
            fcntl.flock(self.handle, fcntl.LOCK_UN)
            self.handle.close()


def _default_agent(cfg):
    argv = require_agent(cfg)
    timeout = None if cfg.agent_timeout_minutes is None else cfg.agent_timeout_minutes * 60

    def run(prompt, cwd, _timeout):
        limit = timeout if _timeout is None else _timeout
        handoff = pathlib.Path(cwd) / cfg.handoff_rel
        handoff.parent.mkdir(parents=True, exist_ok=True)
        handoff.write_text(prompt, encoding="utf-8")
        command = [
            part.replace("{prompt_file}", str(handoff)).replace("{prompt}", prompt).replace("{repo}", str(cwd))
            for part in argv
        ]
        stdin = prompt if cfg.prompt_via == "stdin" else None
        completed = subprocess.run(command, cwd=cwd, input=stdin, text=True, timeout=limit)
        return completed.returncode

    return run


def _run_agent_for_paper(root, cfg, state, run_agent, agent_timeout):
    previous = state["versions"][-1]["paper_sha256"] if state["versions"] else None
    if state["versions"] and state["versions"][-1].get("decision") == "revise":
        number = state["versions"][-1]["n"]
        review_path = str(pathlib.Path(cfg.reviews_rel) / f"v{number:03d}.md")
        review_text = (pathlib.Path(root) / review_path).read_text(encoding="utf-8")
        prompt = papers.agent_prompt(
            "continue", review_path=review_path, review_text=review_text, next_version=number + 1,
        )
    else:
        prompt = papers.agent_prompt("initial", next_version=1)
    last_error = "research agent exited without a new manuscript"
    for _attempt in range(2):
        try:
            code = run_agent(prompt, pathlib.Path(root), agent_timeout)
        except subprocess.TimeoutExpired as exc:
            raise LoopBlock("research agent timed out before writing a new manuscript") from exc
        manuscript = papers.load_manuscript(root, cfg)
        if manuscript is not None and manuscript.paper_sha256 != previous:
            if code not in (0, None):
                print(f"Research agent exited {code} after writing a new manuscript.")
            return manuscript
        last_error = "research agent exited without a new manuscript" if code in (0, None) else f"research agent exited {code} without a new manuscript"
    raise LoopBlock(last_error)


def _close_version(root, cfg, state, git, provider, secret, key_name):
    if _needs_progress(cfg, state):
        _progress_check(root, cfg, state, provider, secret, key_name)
    number = state["versions"][-1]["n"]
    decision = state["versions"][-1].get("decision")
    _sync(git, f"loop: version {number} {decision}")


def _sync(git, message):
    try:
        result = git.commit_and_push(message)
    except GitError as exc:
        raise LoopBlock(f"git sync failed: {exc}") from exc
    print(f"git: {result} ({message})")


def _public(state):
    return {
        "status": state["status"],
        "reason": state.get("reason") or "",
        "versions": len(state["versions"]),
    }


def run_loop(root, *, config=None, env=None, transport=None, run_agent=None, git=None, max_cycles=None):
    root = pathlib.Path(root)
    cfg = config or load_config(root, env)
    env = {} if env is None and config is not None else env
    if git is None:
        git = GitSync(root, remote=cfg.git_remote, enabled=cfg.git_enabled)
    if run_agent is None:
        run_agent = _default_agent(cfg)
    limit = cfg.max_cycles if max_cycles is None else max_cycles
    secret = key_name = None
    provider = None

    def client():
        nonlocal secret, key_name, provider
        if provider is None:
            secret, key_name = require_api_key(cfg, env)
            provider = Provider(cfg, secret, transport=transport)
        return provider

    with _Lock(root):
        state = load_state(root, cfg)
        if state["status"] == "blocked":
            state["status"] = "running"
            state["reason"] = ""
            save_state(root, cfg, state)
        if state["status"] in {"accepted", "stalled"}:
            print(f"Stopped: {state['reason']}")
            return _public(state)
        completed = 0
        try:
            while True:
                if state["status"] in {"accepted", "stalled"}:
                    print(f"Stopped: {state['reason']}")
                    return _public(state)
                if limit is not None and completed >= limit:
                    state["reason"] = f"paused after {completed} cycles"
                    save_state(root, cfg, state)
                    print(state["reason"])
                    return _public(state)
                try:
                    pulled = git.pull()
                except GitError as exc:
                    raise LoopBlock(f"git pull failed: {exc}") from exc
                print(f"git pull: {pulled}")
                state = load_state(root, cfg)
                if state["status"] in {"accepted", "stalled"}:
                    print(f"Stopped: {state['reason']}")
                    return _public(state)
                if state["status"] == "blocked":
                    state["status"] = "running"
                    state["reason"] = ""
                    save_state(root, cfg, state)
                _check_brief(root, cfg, state)
                stop = _scientific_stop(cfg, state)
                if stop:
                    state["status"], state["reason"] = stop
                    save_state(root, cfg, state)
                    _sync(git, f"loop: {state['status']} version {state['versions'][-1]['n']}")
                    print(f"Stopped: {state['reason']}")
                    return _public(state)
                if state["versions"] and state["versions"][-1].get("decision") is None:
                    _finish_open_review(root, cfg, state, client(), secret, key_name)
                    _close_version(root, cfg, state, git, client(), secret, key_name)
                    completed += 1
                    continue
                if _needs_progress(cfg, state):
                    _progress_check(root, cfg, state, client(), secret, key_name)
                    _sync(git, f"loop: progress check version {state['versions'][-1]['n']}")
                    continue
                manuscript = papers.load_manuscript(root, cfg)
                if _unreviewed(state, manuscript):
                    response_text, note = papers.view_for_model(manuscript, _previous_response_sha(state))
                    _review_version(root, cfg, state, client(), secret, key_name, manuscript, response_text, note)
                    _close_version(root, cfg, state, git, client(), secret, key_name)
                    completed += 1
                    continue
                manuscript = _run_agent_for_paper(root, cfg, state, run_agent, None)
                _check_brief(root, cfg, state)
                response_text, note = papers.view_for_model(manuscript, _previous_response_sha(state))
                _review_version(root, cfg, state, client(), secret, key_name, manuscript, response_text, note)
                _close_version(root, cfg, state, git, client(), secret, key_name)
                completed += 1
        except LoopBlock as exc:
            state["status"] = "blocked"
            state["reason"] = str(exc)
            save_state(root, cfg, state)
            print(f"Blocked: {exc}")
            return _public(state)


def run_review_once(root, *, config=None, env=None, transport=None):
    """Send the current manuscript once. Does not advance loop stop state."""
    root = pathlib.Path(root)
    cfg = config or load_config(root, env)
    manuscript = papers.load_manuscript(root, cfg)
    if manuscript is None:
        raise LoopBlock(f"Write the manuscript to {cfg.paper_rel} before requesting a review.")
    secret, key_name = require_api_key(cfg, env)
    provider = Provider(cfg, secret, transport=transport)
    state = load_state(root, cfg)
    response_text, note = papers.view_for_model(manuscript, _previous_response_sha(state))
    print(f"Calling {cfg.strong.provider} model {cfg.strong.model} for a one-shot review.")
    result = _complete_json(
        root, cfg, provider,
        [
            {"role": "system", "content": papers.load_prompt("review.md")},
            {"role": "user", "content": papers.review_user_message(manuscript, response_text, note)},
        ],
        parse_decision,
        operation="review", version=0, secret=secret, key_name=key_name,
    )
    folder = pathlib.Path(root) / cfg.reviews_rel
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "adhoc.md"
    text = result["review_markdown"].rstrip() + "\n"
    path.write_text(text, encoding="utf-8")
    _publish_named_review(root, result, text)
    print(f"One-shot review: {result['decision']} ({path})")
    return result
