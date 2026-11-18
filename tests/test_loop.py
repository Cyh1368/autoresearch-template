"""Supervisor tests. No network. The strong model sees the manuscript only."""
import json, pathlib, shutil, subprocess, tempfile, unittest

from loop.config import load_config
from loop.errors import GitError, LoopBlock, ProviderError
from loop.git_sync import GitSync
from loop.orchestrator import run_loop
from loop.parse import parse_decision, parse_json_object, parse_progress
from loop.provider import Provider
from loop.cli import main
from loop.usage import read_usage

ROOT = pathlib.Path(__file__).resolve().parents[1]
CANARY = "CANARY_EXPERIMENT_DATA_9f3a"
SECRET = "sk-or-v1-" + ("b" * 24)


def workspace():
    root = pathlib.Path(tempfile.mkdtemp(prefix="loop_"))
    (root / "RESEARCH_BRIEF.md").write_text("# Brief\nA bounded question.\n", encoding="utf-8")
    (root / "documents").mkdir()
    (root / "campaign" / "run").mkdir(parents=True)
    (root / "campaign" / "run" / "data.json").write_text(CANARY, encoding="utf-8")
    (root / "documents" / "raw-results.json").write_text(CANARY, encoding="utf-8")
    return root


class FakeGit:
    def __init__(self):
        self.events = []

    def pull(self):
        self.events.append("pull")
        return "no-remote"

    def commit_and_push(self, message):
        self.events.append(message)
        return "pushed"


class Agent:
    def __init__(self, papers, responses=None, code=0):
        self.papers = list(papers)
        self.responses = list(responses or [])
        self.code = code
        self.calls = 0
        self.prompts = []

    def __call__(self, prompt, cwd, timeout):
        self.calls += 1
        self.prompts.append(prompt)
        if not self.papers:
            return self.code
        (cwd / "documents").mkdir(exist_ok=True)
        (cwd / "documents" / "paper.md").write_text(self.papers.pop(0), encoding="utf-8")
        if self.responses:
            (cwd / "documents" / "response.md").write_text(self.responses.pop(0), encoding="utf-8")
        return self.code


class HTTP:
    def __init__(self, decisions=None, progress=False, fail_status=None):
        self.decisions = list(decisions or ["revise"])
        self.progress = progress
        self.fail_status = fail_status
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": headers, "body": body})
        if self.fail_status:
            status = self.fail_status
            self.fail_status = None
            return status, {}, b'{"error":"upstream"}'
        payload = json.loads(body.decode())
        system = payload["messages"][0]["content"]
        if "significant_progress" in system:
            content = json.dumps({
                "significant_progress": self.progress,
                "rationale": "new evidence" if self.progress else "the claim and evidence did not change",
            })
        else:
            decision = self.decisions.pop(0) if len(self.decisions) > 1 else self.decisions[0]
            content = json.dumps({
                "decision": decision,
                "summary": decision,
                "review_markdown": "Review text for the manuscript.",
            })
        envelope = {
            "id": "gen-test",
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18, "cost": 0.02},
        }
        return 200, {}, json.dumps(envelope).encode()


def bodies(http):
    return "\n".join((call["body"] or b"").decode() for call in http.calls)


class LoopTests(unittest.TestCase):
    def setUp(self):
        self.root = workspace()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.env = {"OPENROUTER_API_KEY": SECRET}
        self.git = FakeGit()

    def config(self, **env):
        merged = dict(self.env)
        merged.update(env)
        return load_config(self.root, merged), merged

    def drive(self, agent, http, max_cycles=None, env=None):
        cfg, used = self.config(**(env or {}))
        return run_loop(
            self.root, config=cfg, env=used, transport=http, run_agent=agent,
            git=self.git, max_cycles=max_cycles,
        )

    def test_defaults_are_openrouter_gpt6_sol(self):
        cfg = load_config(self.root, {})
        self.assertEqual(cfg.strong.provider, "openrouter")
        self.assertEqual(cfg.strong.model, "openai/gpt-6-sol")
        self.assertEqual(cfg.strong.api_key_env, "OPENROUTER_API_KEY")
        self.assertEqual(cfg.strong.base_url, "https://openrouter.ai/api/v1")
        self.assertEqual(cfg.strong.key_usage_path, "key")
        self.assertEqual(cfg.stale_window, 3)

    def test_example_config_and_other_providers(self):
        shutil.copy(ROOT / "loop.config.example.json", self.root / "loop.config.json")
        cfg = load_config(self.root, {})
        self.assertEqual(cfg.strong.model, "openai/gpt-6-sol")
        self.assertEqual(cfg.agent_argv[0], "your-agent")
        with self.assertRaises(LoopBlock):
            load_config(self.root, {"AUTORESEARCH_PROVIDER": "anthropic"})
        switched = load_config(self.root, {
            "AUTORESEARCH_PROVIDER": "anthropic",
            "AUTORESEARCH_MODEL": "claude-example",
        })
        self.assertEqual(switched.strong.wire, "anthropic")
        self.assertEqual(switched.strong.base_url, "https://api.anthropic.com")
        self.assertEqual(switched.strong.api_key_env, "ANTHROPIC_API_KEY")
        self.assertIsNone(switched.strong.key_usage_path)
        (self.root / "loop.config.json").write_text(json.dumps({
            "strong_model": {"provider": "openai-compatible", "api_key": SECRET}
        }))
        with self.assertRaises(LoopBlock) as caught:
            load_config(self.root, {})
        self.assertIn("environment", str(caught.exception))
        self.assertNotIn(SECRET, str(caught.exception))

    def test_accept_stops_without_a_progress_call(self):
        http = HTTP(decisions=["accept"])
        agent = Agent(["Paper one is ready."])
        result = self.drive(agent, http)
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(agent.calls, 1)
        self.assertEqual(len(http.calls), 1)
        self.assertIn("Paper one is ready.", bodies(http))
        self.assertNotIn(CANARY, bodies(http))
        self.assertEqual(http.calls[0]["url"], "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(http.calls[0]["headers"]["Authorization"], "Bearer " + SECRET)
        self.assertNotIn(SECRET, (self.root / "usage" / "api-usage.jsonl").read_text())
        self.assertIn("...bbbb", (self.root / "usage" / "api-usage.jsonl").read_text())
        self.assertTrue(any(event.startswith("loop: version 1 accept") for event in self.git.events))
        manifest = json.loads((self.root / "documents" / "versions" / "v001" / "manifest.json").read_text())
        self.assertFalse(manifest["experimental_data_attached"])
        self.assertEqual(manifest["attached"], ["manuscript"])
        self.assertTrue((self.root / "documents" / "REMARK.md").is_file())
        self.assertFalse((self.root / "documents" / "REVIEW.md").exists())

    def test_revise_then_accept_sends_response_and_withholds_stale_one(self):
        http = HTTP(decisions=["revise", "accept"])
        agent = Agent(
            ["Paper A about the pilot.", "Paper B reports the control."],
            responses=["UNIQUE_RESPONSE_ALPHA"],
        )
        result = self.drive(agent, http)
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(agent.calls, 2)
        self.assertEqual(len(http.calls), 2)
        self.assertIn("UNIQUE_RESPONSE_ALPHA", http.calls[0]["body"].decode())
        self.assertNotIn("UNIQUE_RESPONSE_ALPHA", http.calls[1]["body"].decode())
        self.assertIn("unchanged", http.calls[1]["body"].decode())
        self.assertNotIn(CANARY, bodies(http))
        self.assertIn("Review text for the manuscript.", agent.prompts[1])
        self.assertTrue((self.root / "documents" / "REMARK.md").is_file())
        self.assertFalse((self.root / "documents" / "REVIEW.md").exists())

    def test_stalls_when_three_versions_lack_progress(self):
        http = HTTP(decisions=["revise"], progress=False)
        agent = Agent([f"Paper version {i} with the same claim." for i in range(1, 5)])
        result = self.drive(agent, http)
        self.assertEqual(result["status"], "stalled")
        self.assertEqual(agent.calls, 3)
        progress_calls = [call for call in http.calls if b"significant_progress" in call["body"]]
        self.assertEqual(len(progress_calls), 1)
        blob = progress_calls[0]["body"].decode()
        for i in range(1, 4):
            self.assertIn(f"Paper version {i} with the same claim.", blob)
        self.assertNotIn("Paper version 4", blob)
        self.assertNotIn(CANARY, blob)
        self.assertIn("no significant progress", result["reason"])

    def test_progress_lets_the_loop_continue(self):
        http = HTTP(decisions=["revise"], progress=True)
        agent = Agent([f"Paper step {i}." for i in range(1, 6)])
        result = self.drive(agent, http, max_cycles=4)
        self.assertEqual(result["status"], "running")
        self.assertEqual(agent.calls, 4)
        progress_calls = [call for call in http.calls if b"significant_progress" in call["body"]]
        self.assertEqual(len(progress_calls), 2)
        self.assertIn("paused after 4 cycles", result["reason"])

    def test_missing_manuscript_does_not_call_the_model(self):
        http = HTTP()
        agent = Agent([])
        result = self.drive(agent, http)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(http.calls, [])
        self.assertIn("manuscript", result["reason"])
        self.assertEqual(agent.calls, 2)

    def test_missing_key_blocks_before_the_request(self):
        http = HTTP(decisions=["accept"])
        agent = Agent(["Paper without a key."])
        cfg = load_config(self.root, {})
        result = run_loop(
            self.root, config=cfg, env={}, transport=http, run_agent=agent, git=self.git,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertIn("OPENROUTER_API_KEY", result["reason"])
        self.assertEqual(http.calls, [])
        self.assertFalse((self.root / "documents" / "versions").exists())

    def test_http_401_is_not_retried_and_resume_reviews_the_snapshot(self):
        http = HTTP(decisions=["accept"], fail_status=401)
        agent = Agent(["Snapshot paper stays put."])
        first = self.drive(agent, http)
        self.assertEqual(first["status"], "blocked")
        self.assertEqual(len(http.calls), 1)
        self.assertNotIn(SECRET, first["reason"])
        second = self.drive(agent, http)
        self.assertEqual(second["status"], "accepted")
        self.assertEqual(agent.calls, 1)
        self.assertIn("Snapshot paper stays put.", http.calls[-1]["body"].decode())

    def test_server_error_is_retried_once(self):
        http = HTTP(decisions=["accept"], fail_status=500)
        result = self.drive(Agent(["Recovered paper."]), http)
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(len(http.calls), 2)
        rows = read_usage(self.root, load_config(self.root, self.env))
        self.assertEqual([row["status"] for row in rows], ["error", "ok"])

    def test_brief_change_blocks(self):
        http = HTTP()
        agent = Agent([])
        self.drive(agent, http)
        (self.root / "RESEARCH_BRIEF.md").write_text("# Brief\nEdited.\n", encoding="utf-8")
        again = Agent(["Should not run."])
        result = self.drive(again, http)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("RESEARCH_BRIEF.md changed", result["reason"])
        self.assertEqual(again.calls, 0)

    def test_usage_report_and_live_key(self):
        http = HTTP(decisions=["accept"])
        self.drive(Agent(["Usage paper."]), http)

        def live(method, url, headers, body, timeout):
            self.assertEqual(method, "GET")
            self.assertEqual(url, "https://openrouter.ai/api/v1/key")
            self.assertEqual(headers["Authorization"], "Bearer " + SECRET)
            payload = {"data": {
                "label": "sk-or-v1-abc...wxyz",
                "usage": 1.25,
                "usage_daily": 0.1,
                "limit": 10,
                "limit_remaining": 8.75,
                "limit_reset": "monthly",
            }}
            return 200, {}, json.dumps(payload).encode()

        code = main(["usage", "--live"], root=self.root, env=self.env, transport=live)
        self.assertEqual(code, 0)
        offline = main(["usage", "--no-live"], root=self.root, env={})
        self.assertEqual(offline, 0)

    def test_provider_wires(self):
        def grab(method, url, headers, body, timeout):
            grab.seen = (method, url, headers, json.loads(body.decode()))
            if url.endswith("/messages"):
                return 200, {}, json.dumps({
                    "content": [{"type": "text", "text": "anthropic-ok"}],
                    "usage": {"input_tokens": 2, "output_tokens": 3},
                }).encode()
            if ":generateContent" in url:
                return 200, {}, json.dumps({
                    "candidates": [{"content": {"parts": [{"text": "gemini-ok"}]}}],
                    "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 5, "totalTokenCount": 9},
                }).encode()
            return 200, {}, json.dumps({
                "choices": [{"message": {"content": "openai-ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.1},
            }).encode()

        cfg, env = self.config()
        provider = Provider(cfg, SECRET, transport=grab)
        self.assertEqual(provider.complete([{"role": "user", "content": "hi"}]).text, "openai-ok")
        self.assertNotIn("key=", grab.seen[1])
        anth = load_config(self.root, {"AUTORESEARCH_PROVIDER": "anthropic", "AUTORESEARCH_MODEL": "claude-example"})
        text = Provider(anth, "sk-ant-example", transport=grab).complete([
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "hi"},
        ]).text
        self.assertEqual(text, "anthropic-ok")
        self.assertEqual(grab.seen[3]["system"], "rules")
        self.assertEqual(grab.seen[2]["x-api-key"], "sk-ant-example")
        self.assertNotIn("Authorization", grab.seen[2])
        gem = load_config(self.root, {"AUTORESEARCH_PROVIDER": "gemini", "AUTORESEARCH_MODEL": "gemini-example"})
        self.assertEqual(Provider(gem, "AIza-secret", transport=grab).complete([
            {"role": "user", "content": "hi"}
        ]).text, "gemini-ok")
        self.assertNotIn("AIza-secret", grab.seen[1])
        self.assertEqual(grab.seen[2]["x-goog-api-key"], "AIza-secret")
        with self.assertRaises(ProviderError) as caught:
            Provider(cfg, SECRET, transport=lambda *args: (401, {}, SECRET.encode())).complete(
                [{"role": "user", "content": "hi"}]
            )
        self.assertNotIn(SECRET, str(caught.exception))

    def test_fenced_json(self):
        parsed = parse_json_object('```json\n{"decision":"accepted","summary":"ok","review_markdown":"Full."}\n```')
        self.assertEqual(parse_decision(parsed)["decision"], "accept")
        progress = parse_progress(parse_json_object('{"significant_progress":"false","rationale":"same result"}'))
        self.assertFalse(progress["significant_progress"])

    def test_git_skips_env_and_refuses_key_material(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="loop_git_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        origin = tmp / "origin.git"
        work = tmp / "work"
        subprocess.check_call(["git", "init", "--bare", str(origin)], stdout=subprocess.DEVNULL)
        subprocess.check_call(["git", "init", str(work)], stdout=subprocess.DEVNULL)
        subprocess.check_call(["git", "-C", str(work), "config", "user.email", "t@example.com"])
        subprocess.check_call(["git", "-C", str(work), "config", "user.name", "Test"])
        (work / "README").write_text("hello\n", encoding="utf-8")
        subprocess.check_call(["git", "-C", str(work), "add", "README"])
        subprocess.check_call(["git", "-C", str(work), "commit", "-m", "init"], stdout=subprocess.DEVNULL)
        subprocess.check_call(["git", "-C", str(work), "branch", "-M", "main"])
        subprocess.check_call(["git", "-C", str(work), "remote", "add", "origin", str(origin)])
        subprocess.check_call(["git", "-C", str(work), "push", "-u", "origin", "HEAD"], stdout=subprocess.DEVNULL)
        (work / ".env").write_text("OPENROUTER_API_KEY=short\n", encoding="utf-8")
        (work / "notes.md").write_text("a note\n", encoding="utf-8")
        self.assertEqual(GitSync(work).commit_and_push("loop: notes"), "pushed")
        listed = subprocess.check_output(
            ["git", "-C", str(origin), "ls-tree", "-r", "--name-only", "refs/heads/main"], text=True,
        )
        self.assertIn("notes.md", listed)
        self.assertNotIn(".env", listed)
        (work / "leak.txt").write_text("token=" + SECRET + "\n", encoding="utf-8")
        with self.assertRaises(GitError) as caught:
            GitSync(work).commit_and_push("loop: leak")
        self.assertNotIn(SECRET, str(caught.exception))
        listed = subprocess.check_output(
            ["git", "-C", str(origin), "ls-tree", "-r", "--name-only", "refs/heads/main"], text=True,
        )
        self.assertNotIn("leak.txt", listed)


if __name__ == "__main__":
    unittest.main()
