"""Manuscript packaging. The strong model receives the paper and author response only."""
import hashlib, json, pathlib

from loop.errors import LoopBlock

PROMPTS = pathlib.Path(__file__).resolve().parent / "prompts"


def _read_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise LoopBlock(f"{path} is not UTF-8 text") from exc


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Manuscript:
    def __init__(self, paper, response, paper_sha256, response_sha256):
        self.paper = paper
        self.response = response
        self.paper_sha256 = paper_sha256
        self.response_sha256 = response_sha256


def load_manuscript(root, cfg):
    path = pathlib.Path(root) / cfg.paper_rel
    if not path.is_file():
        return None
    paper = _read_text(path)
    if not paper.strip():
        return None
    response = None
    response_sha = None
    response_path = pathlib.Path(root) / cfg.response_rel
    if response_path.is_file():
        text = _read_text(response_path)
        if text.strip():
            response = text
            response_sha = _sha(text)
    return Manuscript(paper, response, _sha(paper), response_sha)


def view_for_model(manuscript, previous_response_sha):
    """Return the response text to attach, plus a note when a stale response is withheld."""
    if manuscript.response is None:
        return None, None
    if previous_response_sha and manuscript.response_sha256 == previous_response_sha:
        return None, "The author response file was unchanged from the previous version and was withheld."
    return manuscript.response, None


def version_dir(root, cfg, number):
    return pathlib.Path(root) / cfg.versions_rel / f"v{number:03d}"


def snapshot(root, cfg, number, manuscript, response_text, note):
    dest = version_dir(root, cfg, number)
    if dest.exists():
        raise LoopBlock(
            f"{dest} already exists. Refusing to overwrite a manuscript version. "
            "Remove documents/loop-state.json together with documents/versions only when restarting the run."
        )
    dest.mkdir(parents=True)
    (dest / "paper.md").write_text(manuscript.paper, encoding="utf-8")
    attached = ["manuscript"]
    if response_text is not None:
        (dest / "response.md").write_text(response_text, encoding="utf-8")
        attached.append("author response")
    manifest = {
        "version": number,
        "paper_sha256": manuscript.paper_sha256,
        "response_sha256": manuscript.response_sha256 if response_text is not None else None,
        "attached": attached,
        "note": note,
        "experimental_data_attached": False,
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def review_user_message(manuscript, response_text, note):
    parts = [
        "Attached evidence is the manuscript and, when present, the author response.",
        "",
        "Manuscript:",
        "",
        manuscript.paper,
    ]
    if response_text is not None:
        parts.extend(["", "Author response:", "", response_text])
    elif note:
        parts.extend(["", note])
    else:
        parts.extend(["", "No author response was provided."])
    return "\n".join(parts) + "\n"


def progress_user_message(root, cfg, versions):
    chunks = ["Judge these versions in order.", ""]
    root = pathlib.Path(root)
    for item in versions:
        number = item["n"]
        folder = version_dir(root, cfg, number)
        paper = _read_text(folder / "paper.md")
        chunks.append(f"## Version {number}")
        chunks.append("")
        chunks.append("### Manuscript")
        chunks.append("")
        chunks.append(paper)
        chunks.append("")
        response_path = folder / "response.md"
        chunks.append("### Author response")
        chunks.append("")
        if item.get("response_sent") and response_path.is_file():
            chunks.append(_read_text(response_path))
        else:
            chunks.append("None was sent for this version.")
        chunks.append("")
        review_path = root / cfg.reviews_rel / f"v{number:03d}.md"
        review = _read_text(review_path) if review_path.is_file() else ""
        chunks.append("### Review decision")
        chunks.append("")
        chunks.append(str(item.get("decision") or "pending"))
        chunks.append("")
        chunks.append("### Review")
        chunks.append("")
        chunks.append(review or "No review text was recorded.")
        chunks.append("")
    return "\n".join(chunks)


def load_prompt(name):
    return (PROMPTS / name).read_text(encoding="utf-8")


def agent_prompt(kind, *, review_path="", review_text="", next_version=1):
    filename = "agent_initial.md" if kind == "initial" else "agent_continue.md"
    text = load_prompt(filename)
    return (
        text.replace("{review_path}", review_path or "")
        .replace("{review}", review_text or "")
        .replace("{next_version}", str(next_version))
    )
