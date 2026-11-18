"""Parse the strong model's JSON decision. Accept only an explicit accept."""
import json, re


def parse_json_object(text):
    raw = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, flags=re.DOTALL)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("model reply did not contain a JSON object")
        value = json.loads(raw[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("model JSON must be an object")
    return value


def parse_decision(obj):
    raw = str(obj.get("decision", "")).strip().lower().replace("-", " ").replace("_", " ")
    raw = " ".join(raw.split())
    if raw in {"accept", "accepted"}:
        decision = "accept"
    elif raw in {"revise", "revision", "reject", "rejected"}:
        decision = "revise"
    else:
        raise ValueError("decision must be accept or revise")
    review = str(obj.get("review_markdown") or obj.get("review") or "").strip()
    if not review:
        raise ValueError("review_markdown is required")
    summary = str(obj.get("summary") or "").strip()
    return {"decision": decision, "summary": summary, "review_markdown": review}


def combine_reviews(reviews):
    """Accept only when three reviewers accept. Otherwise return one revise text."""
    if len(reviews) != 3:
        raise ValueError("a panel requires three reviews")
    accepted = all(item.get("decision") == "accept" for item in reviews)
    decision = "accept" if accepted else "revise"
    if accepted:
        summary = "All three reviewers accepted the manuscript."
        intro = "All three reviewers accepted this manuscript. Their remarks follow."
    else:
        summary = "The panel did not reach unanimous acceptance."
        intro = (
            "Acceptance requires three reviewers, and all three must accept. "
            "The panel did not. The three reviews follow."
        )
    parts = [intro, ""]
    for index, item in enumerate(reviews, start=1):
        parts.append(f"## Reviewer {index} ({item['decision']})")
        parts.append("")
        line = str(item.get("summary") or "").strip()
        if line:
            parts.append(line)
            parts.append("")
        parts.append(str(item.get("review_markdown") or "").strip())
        parts.append("")
    return {
        "decision": decision,
        "summary": summary,
        "review_markdown": "\n".join(parts).rstrip() + "\n",
        "reviews": list(reviews),
    }


def parse_progress(obj):
    if "significant_progress" not in obj:
        raise ValueError("significant_progress is required")
    value = obj["significant_progress"]
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            value = True
        elif lowered == "false":
            value = False
        else:
            raise ValueError("significant_progress must be a boolean")
    if not isinstance(value, bool):
        raise ValueError("significant_progress must be a boolean")
    rationale = str(obj.get("rationale") or "").strip()
    if not rationale:
        raise ValueError("rationale is required")
    return {"significant_progress": value, "rationale": rationale}
