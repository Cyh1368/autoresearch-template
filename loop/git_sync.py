"""Pull, commit, and push the repo. Refuse secrets. Do not rewrite history."""
import re, subprocess
from pathlib import Path

from loop.errors import GitError
from loop.secrets import _KEY

_SENSITIVE = re.compile(
    r"(^|/)(\.env($|\.)|.*\.pem$|.*\.key$|id_rsa|credentials\.json$|.*service-account.*)$",
    re.IGNORECASE,
)


class GitSync:
    def __init__(self, root, remote="origin", enabled=True, run=None):
        self.root = Path(root)
        self.remote = remote
        self.enabled = enabled
        self._run = run or _git

    def pull(self):
        if not self.enabled:
            return "disabled"
        self._ensure_repo()
        if not self._has_remote():
            return "no-remote"
        branch = self._branch()
        if self._has_upstream():
            self._run(self.root, ["pull", "--rebase", "--autostash", self.remote, branch])
            return "pulled"
        return "no-upstream"

    def commit_and_push(self, message):
        if not self.enabled:
            return "disabled"
        self._ensure_repo()
        self._run(self.root, ["add", "-A"])
        self._unstage_sensitive()
        self._refuse_key_material()
        committed = False
        if self._has_staged():
            self._run(self.root, ["commit", "-m", message])
            committed = True
        if not self._has_remote():
            return "committed" if committed else "clean"
        self._run(self.root, ["push", "-u", self.remote, "HEAD"])
        return "pushed" if committed else "pushed-existing"

    def _ensure_repo(self):
        probe = subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True,
        )
        if probe.returncode != 0 or probe.stdout.strip() != "true":
            raise GitError(f"{self.root} is not a git repository. Set git.enabled to false to run without sync.")

    def _has_remote(self):
        probe = subprocess.run(
            ["git", "-C", str(self.root), "remote", "get-url", self.remote],
            capture_output=True, text=True,
        )
        return probe.returncode == 0

    def _has_upstream(self):
        probe = subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            capture_output=True, text=True,
        )
        return probe.returncode == 0

    def _branch(self):
        result = self._run(self.root, ["rev-parse", "--abbrev-ref", "HEAD"])
        name = result.strip()
        if not name or name == "HEAD":
            raise GitError("detached HEAD. Check out a branch before the loop syncs git.")
        return name

    def _unstage_sensitive(self):
        listed = subprocess.run(
            ["git", "-C", str(self.root), "diff", "--cached", "--name-only", "-z"],
            capture_output=True, text=True, check=True,
        )
        bad = [path for path in listed.stdout.split("\0") if path and _SENSITIVE.search(path)]
        if bad:
            self._run(self.root, ["restore", "--staged", "--", *bad])

    def _refuse_key_material(self):
        listed = subprocess.run(
            ["git", "-C", str(self.root), "diff", "--cached", "--name-only"],
            capture_output=True, text=True, check=True,
        )
        for path in [line for line in listed.stdout.splitlines() if line.strip()]:
            diff = subprocess.run(
                ["git", "-C", str(self.root), "diff", "--cached", "--", path],
                capture_output=True, text=True, check=True,
            )
            if _KEY.search(diff.stdout):
                self._unstage_all()
                raise GitError(f"refusing to commit {path}: it contains an API key")

    def _unstage_all(self):
        probe = subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "--verify", "HEAD"],
            capture_output=True,
        )
        if probe.returncode == 0:
            subprocess.run(["git", "-C", str(self.root), "reset", "-q"], check=True)
            return
        subprocess.run(["git", "-C", str(self.root), "rm", "-r", "--cached", "-q", "."], check=False)

    def _has_staged(self):
        probe = subprocess.run(
            ["git", "-C", str(self.root), "diff", "--cached", "--quiet"],
            capture_output=True,
        )
        return probe.returncode == 1


def _git(root, args):
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "git failed").strip()
        raise GitError(detail.splitlines()[-1][:500])
    return completed.stdout
