"""One manuscript version per research-agent process, then a strong-model review.

A rejection from the first reviewer ends that round. An acceptance is sent to
two more reviewers, and both must accept before the campaign can finish.
``reopen_campaign`` archives an accepted or stalled round after the human
replaces the research brief, so the interactive session can start another.
"""
import fcntl, hashlib, json, pathlib, shutil, subprocess

from loop import manuscript as papers
from loop.config import load_config, require_agent, require_api_key
from loop.errors import GitError, LoopBlock, ProviderError
from loop.git_sync import GitSync
from loop.parse import combine_reviews, parse_decision, parse_json_object, parse_progress
from loop.provider import Provider
from loop.secrets import key_hint
from loop.state import empty_state, load_state, save_state
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
            "RESEARCH_BRIEF.md changed after this round started. "
            "Keep this loop state. A new proposal is adopted with bin/autoresearch reopen "
            "only after the round is accepted or stalled."
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


_PANEL_SIZE = 3


def _review_record(role, result):
    return {
        "role": role,
        "decision": result["decision"],
        "summary": result.get("summary") or "",
        "review_markdown": result["review_markdown"],
    }


def _snapshot_view(root, cfg, item):
    folder = papers.version_dir(root, cfg, item["n"])
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))

    class _Snap:
        pass

    snap = _Snap()
    snap.paper = (folder / "paper.md").read_text(encoding="utf-8")
    response_text = None
    if item.get("response_sent"):
        response_text = (folder / "response.md").read_text(encoding="utf-8")
    return snap, response_text, manifest.get("note")


def _call_review(root, cfg, provider, secret, key_name, number, snap, response_text, note, operation, reviewer_index):
    return _complete_json(
        root, cfg, provider,
        [
            {"role": "system", "content": papers.load_prompt("review.md")},
            {
                "role": "user",
                "content": papers.review_user_message(
                    snap, response_text, note, reviewer_index=reviewer_index,
                ),
            },
        ],
        parse_decision,
        operation=operation, version=number, secret=secret, key_name=key_name,
    )


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
    if result.get("summary") and not result.get("reviews"):
        body = result["summary"] + "\n\n" + body
    text = body.rstrip() + "\n"
    path.write_text(text, encoding="utf-8")
    _publish_named_review(root, result, text)
    payload = {"version": number, "decision": result["decision"], "summary": result.get("summary", "")}
    if result.get("reviews"):
        payload["panel"] = [
            {"role": item["role"], "decision": item["decision"], "summary": item.get("summary", "")}
            for item in result["reviews"]
        ]
    (folder / f"v{number:03d}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _apply_decision(state, number, result):
    state["versions"][-1]["decision"] = result["decision"]
    if result["decision"] == "accept":
        state["status"] = "accepted"
        if result.get("reviews"):
            state["reason"] = f"accepted by three reviewers at version {number}"
        else:
            state["reason"] = f"accepted at version {number}"
    else:
        state["status"] = "running"
        if result.get("reviews"):
            state["reason"] = f"revise at version {number}: the panel did not all accept"
        else:
            state["reason"] = f"revise at version {number}"


def _confirm_panel(root, cfg, state, provider, secret, key_name):
    """Call the two reviewers still required after the first acceptance."""
    item = state["versions"][-1]
    panel = item["panel"]
    number = item["n"]
    snap, response_text, note = _snapshot_view(root, cfg, item)
    while len(panel["reviews"]) < _PANEL_SIZE:
        slot = len(panel["reviews"])
        print(
            f"Calling {cfg.strong.provider} model {cfg.strong.model} "
            f"for confirmation review {slot} of {_PANEL_SIZE - 1} on version {number}."
        )
        result = _call_review(
            root, cfg, provider, secret, key_name, number, snap, response_text, note,
            "confirmation", slot + 1,
        )
        panel["reviews"].append(_review_record("confirmation", result))
        save_state(root, cfg, state)
        print(f"Confirmation {slot} of version {number}: {result['decision']}")
    combined = combine_reviews(panel["reviews"])
    panel["phase"] = "closed"
    path = _write_review(root, cfg, number, combined)
    _apply_decision(state, number, combined)
    save_state(root, cfg, state)
    print(f"Panel of version {number}: {combined['decision']} ({path})")
    return combined


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
    return _finish_open_review(root, cfg, state, provider, secret, key_name)


def _finish_open_review(root, cfg, state, provider, secret, key_name):
    """Review a snapshot that was saved before an earlier call failed.

    An open panel keeps the reviewers who already answered and calls only the rest.
    """
    item = state["versions"][-1]
    number = item["n"]
    panel = item.get("panel") or {}
    if panel.get("phase") == "confirming":
        return _confirm_panel(root, cfg, state, provider, secret, key_name)
    snap, response_text, note = _snapshot_view(root, cfg, item)
    print(f"Calling {cfg.strong.provider} model {cfg.strong.model} for review of version {number}.")
    result = _call_review(
        root, cfg, provider, secret, key_name, number, snap, response_text, note, "review", None,
    )
    if result["decision"] != "accept":
        path = _write_review(root, cfg, number, result)
        _apply_decision(state, number, result)
        save_state(root, cfg, state)
        print(f"Review of version {number}: revise ({path})")
        return result
    item["panel"] = {"phase": "confirming", "reviews": [_review_record("primary", result)]}
    save_state(root, cfg, state)
    print(
        f"Reviewer 1 accepted version {number}. "
        "Two more reviewers must accept before the work can finish."
    )
    return _confirm_panel(root, cfg, state, provider, secret, key_name)


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
            raise LoopBlock("Another autoresearch submit or loop is already running in this repository.") from exc
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


_BRIEF_PLACEHOLDERS = ("[Question", "[Systems", "[Scope")


def _live_payloads(root, cfg):
    """Files a finished round leaves in documents/ for the agent to read."""
    documents = pathlib.Path(root) / "documents"
    paths = [
        pathlib.Path(root) / cfg.paper_rel,
        pathlib.Path(root) / cfg.response_rel,
        documents / "REVIEW.md",
        documents / "REMARK.md",
        pathlib.Path(root) / cfg.versions_rel,
        pathlib.Path(root) / cfg.reviews_rel,
        pathlib.Path(root) / cfg.progress_rel,
    ]
    return [path for path in paths if path.exists()]


def _round_dirs(root):
    rounds = pathlib.Path(root) / "documents" / "rounds"
    if not rounds.is_dir():
        return []
    found = []
    for path in rounds.iterdir():
        name = path.name
        if path.is_dir() and len(name) >= 4 and name[:3].isdigit() and name[3] == "-":
            found.append(path)
    return sorted(found)


def _matching_round(root, state):
    """Return the archive of this finished round when a previous reopen already wrote it."""
    found = _round_dirs(root)
    if not found:
        return None
    newest = found[-1]
    manifest_path = newest / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if manifest.get("brief_sha256") != state.get("brief_sha256"):
        return None
    if manifest.get("status") != state.get("status"):
        return None
    if manifest.get("reason") != (state.get("reason") or ""):
        return None
    return newest


def _remove_path(path):
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _archive_round(root, cfg, state, payloads):
    rounds = pathlib.Path(root) / "documents" / "rounds"
    rounds.mkdir(parents=True, exist_ok=True)
    if any(rounds.glob(".staging-*")):
        raise LoopBlock(
            "A previous reopen left a documents/rounds/.staging-* directory. "
            "Remove it after checking the live round is intact."
        )
    found = _round_dirs(root)
    number = int(found[-1].name.split("-", 1)[0]) + 1 if found else 1
    name = f"{number:03d}-{state['status']}"
    staging = rounds / f".staging-{name}"
    dest = rounds / name
    staging.mkdir()
    try:
        archived = []
        state_path = pathlib.Path(root) / cfg.state_rel
        shutil.copy2(state_path, staging / state_path.name)
        archived.append(state_path.name)
        for path in payloads:
            if path.is_dir():
                shutil.copytree(path, staging / path.name)
                archived.append(path.name + "/")
            else:
                shutil.copy2(path, staging / path.name)
                archived.append(path.name)
        manifest = {
            "status": state["status"],
            "reason": state.get("reason") or "",
            "brief_sha256": state.get("brief_sha256"),
            "versions": [item.get("n") for item in state.get("versions") or []],
            "archived": archived,
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
        )
        staging.rename(dest)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return dest


def _adopt_brief(root, cfg, state):
    status = state.get("status")
    if status not in {"accepted", "stalled"}:
        raise LoopBlock(
            f"This round is {status}. Reopen waits until the round is accepted or stalled. "
            "Keep this state."
        )
    if not state.get("brief_sha256"):
        raise LoopBlock("This round has no pinned brief hash. Keep this state.")
    digest = _brief_sha(root)
    brief_path = pathlib.Path(root) / "RESEARCH_BRIEF.md"
    try:
        brief = brief_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise LoopBlock("RESEARCH_BRIEF.md is not UTF-8 text.") from exc
    for marker in _BRIEF_PLACEHOLDERS:
        if marker in brief:
            raise LoopBlock(
                "Brief incomplete: required section still holds placeholder " + marker + "..."
            )
    if digest == state["brief_sha256"]:
        raise LoopBlock(
            "RESEARCH_BRIEF.md is unchanged. Write the new proposal there before reopening. "
            "This finished round stays in place."
        )
    payloads = _live_payloads(root, cfg)
    finished = _matching_round(root, state)
    if finished is None:
        finished = _archive_round(root, cfg, state, payloads)
    for path in payloads:
        _remove_path(path)
    relative = finished.relative_to(root).as_posix()
    fresh = empty_state()
    fresh["brief_sha256"] = digest
    fresh["status"] = "running"
    fresh["reason"] = f"reopened after {status}; previous round is {relative}"
    fresh["previous_round"] = relative
    save_state(root, cfg, fresh)
    return relative


def reopen_campaign(root, *, config=None, env=None):
    """Archive an accepted or stalled round and pin the brief the human just wrote.

    Does not call the strong model and does not sync git. The next manuscript
    goes through submit. A refusal leaves the finished round where it is.
    """
    root = pathlib.Path(root)
    cfg = config or load_config(root, env)
    with _Lock(root):
        state = load_state(root, cfg)
        try:
            relative = _adopt_brief(root, cfg, state)
        except LoopBlock as exc:
            print(f"Blocked: {exc}")
            return {
                "status": "blocked",
                "reason": str(exc),
                "versions": len(state.get("versions") or []),
            }
    print(f"Reopened. Previous round is {relative}.")
    print(
        "Write a new policy.json from RESEARCH_BRIEF.md, run bin/autoresearch init, "
        "and write a new documents/paper.md."
    )
    print("Then run bin/autoresearch submit, sleep 600 seconds, and follow the line it prints.")
    return _public(load_state(root, cfg))


def _tell_agent(state):
    """Print the next step for an interactive agent session."""
    if state["status"] == "accepted":
        print("Read documents/REMARK.md and stop.")
        return
    if state["status"] == "stalled":
        print("Read documents/loop-state.json. This campaign is stalled. Stop.")
        return
    if state["status"] == "blocked":
        print("Read documents/loop-state.json and stop. A person has to clear this block.")
        return
    print("Sleep 600 seconds, then read documents/REVIEW.md and continue.")


def submit_manuscript(root, *, config=None, env=None, transport=None, git=None):
    """Review the manuscript the interactive agent already wrote.

    Does not start a research agent. The caller sleeps and then reads the files
    this function names.
    """
    root = pathlib.Path(root)
    cfg = config or load_config(root, env)
    env = {} if env is None and config is not None else env
    if git is None:
        git = GitSync(root, remote=cfg.git_remote, enabled=cfg.git_enabled)
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
            _tell_agent(state)
            return _public(state)
        try:
            try:
                pulled = git.pull()
            except GitError as exc:
                raise LoopBlock(f"git pull failed: {exc}") from exc
            print(f"git pull: {pulled}")
            state = load_state(root, cfg)
            if state["status"] in {"accepted", "stalled"}:
                print(f"Stopped: {state['reason']}")
                _tell_agent(state)
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
                _tell_agent(state)
                return _public(state)
            if state["versions"] and state["versions"][-1].get("decision") is None:
                _finish_open_review(root, cfg, state, client(), secret, key_name)
                _close_version(root, cfg, state, git, client(), secret, key_name)
            elif _needs_progress(cfg, state):
                _progress_check(root, cfg, state, client(), secret, key_name)
                _sync(git, f"loop: progress check version {state['versions'][-1]['n']}")
            else:
                manuscript = papers.load_manuscript(root, cfg)
                if manuscript is None:
                    raise LoopBlock(
                        f"Write the manuscript to {cfg.paper_rel} before bin/autoresearch submit."
                    )
                if _unreviewed(state, manuscript):
                    response_text, note = papers.view_for_model(
                        manuscript, _previous_response_sha(state)
                    )
                    _review_version(
                        root, cfg, state, client(), secret, key_name,
                        manuscript, response_text, note,
                    )
                    _close_version(root, cfg, state, git, client(), secret, key_name)
                else:
                    last = state["versions"][-1]
                    print(
                        f"Version {last['n']} is already reviewed ({last.get('decision')}). "
                        "No new strong-model call."
                    )
            if state["status"] in {"accepted", "stalled"}:
                print(f"Stopped: {state['reason']}")
            _tell_agent(state)
            return _public(state)
        except LoopBlock as exc:
            state["status"] = "blocked"
            state["reason"] = str(exc)
            save_state(root, cfg, state)
            print(f"Blocked: {exc}")
            _tell_agent(state)
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
