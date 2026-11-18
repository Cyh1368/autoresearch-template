"""End-to-end lifecycle tests for a real (human-supplied) research brief.

Each test runs against an isolated copy of the template in a temp dir so the
template working tree is never modified. Only the stdlib is used.
"""
import json, os, pathlib, shutil, subprocess, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

GOOD_BRIEF = """# Research brief
## 1. Research direction (required)
Measure whether sorted() beats a naive quicksort on 1000 random ints.
## 3. Experimental setting (required)
Single Python process, one core, fixed seeds.
## 4. Allowed resources (required)
Local execution only inside the current allocation. 1 CPU, 512 MB, 0 GPU,
5 minutes, 3 attempts, no Slurm, no network, no GPU, no other partitions.
## 6. Evaluation preferences (optional)
Report wall-clock seconds per condition.
## 7. Limitations and constraints (optional)
Single machine; not a general hardware claim.
"""

GOOD_POLICY = {
    "allow_local": True, "allow_slurm": False, "partitions": [],
    "cpus_max": 1, "memory_mb_max": 512, "gpus_max": 0, "wall_minutes_max": 5,
    "concurrency_max": 1, "attempts_max": 3, "elapsed_hours_max": 0.25,
    "storage_mb_max": 32,
}


def fresh_copy():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="art_life_"))
    dst = tmp / "template"
    shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(".git", "__pycache__", "output"))
    return tmp, dst


def run(dst, args, env=None, policy=None):
    e = dict(os.environ)
    if env is not None:
        e.update(env)
    return subprocess.run([str(dst / "bin" / "autoresearch")] + args,
                          cwd=dst, env=e, capture_output=True, text=True)


def run_job(dst, args, env=None):
    e = dict(os.environ)
    if env is not None:
        e.update(env)
    return subprocess.run([str(dst / "bin" / "research-job")] + args,
                          cwd=dst, env=e, capture_output=True, text=True)


def write_inputs(dst, brief=GOOD_BRIEF, policy=None):
    (dst / "RESEARCH_BRIEF.md").write_text(brief)
    (dst / "policy.json").write_text(json.dumps(policy or GOOD_POLICY))


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp, self.dst = fresh_copy()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def campaigns(self):
        camp = self.dst / "campaign"
        return sorted(p.name for p in camp.iterdir()
                      if p.is_dir() and (p / "state.json").exists())

    # --- brief / policy validation -------------------------------------------
    def test_incomplete_brief_rejected_cleanly(self):
        text = (self.dst / "RESEARCH_BRIEF.md").read_text()
        (self.dst / "RESEARCH_BRIEF.md").write_text(text + "\n[Question]\n")
        (self.dst / "policy.json").write_text(json.dumps(GOOD_POLICY))
        p = run(self.dst, ["init"])
        self.assertEqual(p.returncode, 1)
        self.assertIn("Brief incomplete", p.stdout + p.stderr)
        self.assertNotIn("Traceback", p.stdout + p.stderr)
        self.assertEqual(self.campaigns(), [])

    def test_required_limitations_placeholder_rejected(self):
        # Section 7 (required) left as its placeholder must be caught.
        brief = GOOD_BRIEF.replace("Single machine; not a general hardware claim.",
                                   "[Scope, privacy, access, assumptions]")
        write_inputs(self.dst, brief=brief)
        p = run(self.dst, ["init"])
        self.assertEqual(p.returncode, 1)
        self.assertIn("[Scope", p.stdout + p.stderr)
        self.assertEqual(self.campaigns(), [])

    def test_invalid_policy_rejected(self):
        bad = dict(GOOD_POLICY); bad.pop("cpus_max")
        write_inputs(self.dst, policy=bad)
        p = run(self.dst, ["init"])
        self.assertEqual(p.returncode, 1)
        self.assertIn("policy must contain exactly", p.stdout + p.stderr)

    def test_no_execution_mode_authorized_rejected(self):
        bad = dict(GOOD_POLICY); bad["allow_local"] = False
        write_inputs(self.dst, policy=bad)
        p = run(self.dst, ["init"])
        self.assertEqual(p.returncode, 1)
        self.assertIn("no execution mode authorized", p.stdout + p.stderr)

    # --- happy path ----------------------------------------------------------
    def test_full_lifecycle(self):
        write_inputs(self.dst)
        p = run(self.dst, ["init"])
        self.assertEqual(p.returncode, 0, p.stderr)
        cids = self.campaigns()
        self.assertEqual(len(cids), 1)
        cdir = self.dst / "campaign" / cids[0]
        for name in ("brief.snapshot.md", "policy.json", "state.json",
                     "experiment-ledger.jsonl", "findings.md", "protocol.md"):
            self.assertTrue((cdir / name).exists(), name)

        # status reports the campaign and its policy
        s = run(self.dst, ["status"])
        self.assertEqual(s.returncode, 0, s.stderr)
        info = json.loads(s.stdout)
        self.assertEqual(info["policy"], GOOD_POLICY)
        self.assertEqual(info["state"]["status"], "ready")

        # report with one ledger row
        with (cdir / "experiment-ledger.jsonl").open("a") as fh:
            fh.write(json.dumps({"exp": "exp0", "status": "ok", "result": "x"}) + "\n")
        r = run(self.dst, ["report"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Experiments: 1", (cdir / "report.md").read_text())

        # graceful stop does not cancel jobs, just drops a STOP marker
        st = run(self.dst, ["stop"])
        self.assertEqual(st.returncode, 0, st.stderr)
        self.assertTrue((cdir / "STOP").exists())

    def test_brief_change_after_init_is_blocked(self):
        write_inputs(self.dst)
        self.assertEqual(run(self.dst, ["init"]).returncode, 0)
        (self.dst / "RESEARCH_BRIEF.md").write_text(GOOD_BRIEF + "\nEDITED\n")
        s = run(self.dst, ["status"])
        self.assertEqual(s.returncode, 1)
        self.assertIn("brief changed", s.stdout + s.stderr)
        self.assertNotIn("Traceback", s.stdout + s.stderr)

    # --- research-job guard rails -------------------------------------------
    def test_local_requires_allocation(self):
        write_inputs(self.dst)
        run(self.dst, ["init"])
        cid = self.campaigns()[0]
        pol = self.dst / "campaign" / cid / "policy.json"
        p = run_job(self.dst, ["local", str(pol), "echo", "hi"], env={"SLURM_JOB_ID": ""})
        # empty string is falsy -> must be rejected
        self.assertEqual(p.returncode, 1)
        self.assertIn("active Slurm allocation", p.stdout + p.stderr)

    def test_local_not_authorized_rejected(self):
        pol = dict(GOOD_POLICY); pol["allow_local"] = False; pol["allow_slurm"] = True
        pol["partitions"] = ["devel"]
        write_inputs(self.dst, policy=pol)
        run(self.dst, ["init"])
        cid = self.campaigns()[0]
        p = run_job(self.dst, ["local", "policy.json", "echo", "hi"])
        self.assertEqual(p.returncode, 1)
        self.assertIn("local execution not authorized", p.stdout + p.stderr)

    def test_slurm_mode_fail_closed(self):
        pol = dict(GOOD_POLICY); pol["allow_slurm"] = True; pol["partitions"] = ["devel"]
        write_inputs(self.dst, policy=pol)
        run(self.dst, ["init"])
        p = run_job(self.dst, ["slurm", "policy.json", "echo", "hi"])
        self.assertEqual(p.returncode, 1)
        self.assertIn("validated policy", p.stdout + p.stderr)

    def test_local_experiment_executes_in_allocation(self):
        if not os.environ.get("SLURM_JOB_ID"):
            self.skipTest("real local execution requires an active Slurm allocation")
        write_inputs(self.dst)
        run(self.dst, ["init"])
        cid = self.campaigns()[0]
        cdir = self.dst / "campaign" / cid
        pol = cdir / "policy.json"
        p = run_job(self.dst, ["local", str(pol), "python3", "-c", "print(6*7)"])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("42", p.stdout)


if __name__ == "__main__":
    unittest.main()
