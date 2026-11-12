# Autoresearch template

A transparent starter for computational research controlled by one natural-language brief. The live coding agent owns the iterative loop; the CLI provides deterministic checks and state helpers and does not launch a coding agent in the background. The policy file is agent-derived and must be reviewed against the brief; language interpretation is not a security boundary.

## How it works

The system splits responsibility between a human brief, the live coding agent (the
controller), and a small deterministic, stdlib-only helper (`core/runner.py` behind
`bin/autoresearch` and `bin/research-job`). The helper never interprets prose into
permissions and never submits cluster jobs on its own — it only enforces the fields
that were explicitly recorded in a policy file and refuses anything else.

Control flow for one campaign:

```
RESEARCH_BRIEF.md  (human-edited, natural language)
        │  agent reads brief + AGENT_INSTRUCTIONS.md and derives a bounded policy
        ▼
policy.json        (11 fixed keys; agent-authored, reviewed against the brief)
        │  bin/autoresearch init  → snapshot+hash the brief, validate policy
        ▼
campaign/<id>/     (immutable per-campaign record: state, ledger, findings, protocol)
        │  live agent runs the loop: hypothesis → isolated experiment dir + manifest
        ▼
bin/research-job   (the ONLY execution path; fail-closed)
        │  measure → validate nonempty result → analyze → record (incl. failures)
        ▼
experiment-ledger.jsonl / findings.md  →  bin/autoresearch report
```

- **The controller is the foreground coding-agent process.** If its interface exits,
  the loop pauses; nothing is resubmitted automatically. A submitted experiment job
  can outlive the controller, so reconcile scheduler state before starting new work.
- **Two execution paths, both fail-closed** (`bin/research-job {local|slurm} POLICY.json COMMAND...`):
  - `local` runs the command only if the policy sets `allow_local` **and** an active
    Slurm allocation is present (`SLURM_JOB_ID`). No allocation means it refuses; the
    tiny offline `smoke` mode is the only thing that runs without one.
  - `slurm` always refuses: this helper accepts only a validated policy, not a signed
    site-specific job request, so real Slurm submission is intentionally not automated.
- **Policy is recorded, not enforced.** `validate_policy` checks that the 11 keys are
  present and well-formed (booleans, nonnegative numbers, `allow_slurm` requires
  explicit `partitions`, and at least one of local/slurm authorized). It does **not**
  cap CPU/memory/time/GPU at runtime — the agent must self-police against the brief.
- **Campaign integrity.** `init` refuses a brief that still holds a required-section
  placeholder and refuses to invent policy; it snapshots the brief and stores its
  SHA-256. Any later edit to `RESEARCH_BRIEF.md` makes `status`/`report` stop with
  "brief changed" — keep the old campaign and initialize a new one explicitly.
  `stop` drops a `STOP` marker to pause new work and never cancels active jobs.

### Commands

| Command | Effect |
| --- | --- |
| `bin/autoresearch check` | Report Python version and whether `sbatch`/`squeue` are available. |
| `bin/autoresearch init` | Validate the brief and `./policy.json`, then create `campaign/<id>/`. |
| `bin/autoresearch start` | Print a reminder that the foreground agent runs the loop. |
| `bin/autoresearch status` | Print the current campaign's state and policy as JSON (verifies brief hash). |
| `bin/autoresearch report` | Write `report.md` (status + experiment count) for the current campaign. |
| `bin/autoresearch stop` | Request a graceful stop (drops `STOP`; does not cancel jobs). |
| `bin/autoresearch smoke` | Run the offline mechanics demo in `examples/smoke_test/`. |
| `bin/research-job {local\|slurm} POLICY.json CMD...` | The only sanctioned execution path (see above). |

`init` reads `./policy.json` from the current working directory, so run it from the
repository root. `current()` selects the most recent `campaign/<id>` by name.

### Layout

- `RESEARCH_BRIEF.md` — the only human-edited input (sections 1, 3, 4, 7 are required).
- `AGENT_INSTRUCTIONS.md` — the operating protocol the live agent follows.
- `core/runner.py` — deterministic state/experiment controls (stdlib only).
- `bin/autoresearch`, `bin/research-job` — thin CLI wrappers.
- `campaign/<id>/` — per-campaign records: `brief.snapshot.md`, `policy.json`,
  `state.json`, `experiment-ledger.jsonl`, `findings.md`, `protocol.md`, and one
  isolated directory per experiment. Generated; never edit or overwrite.
- `examples/smoke_test/` — offline demo (writes to a gitignored `output/`), not research.
- `slurm/agent-session.example.sh` — illustrative session notes only.

## Quick start

1. Copy this directory to the campaign project and edit only `RESEARCH_BRIEF.md`.
2. Obtain a Bouchet agent-partition session under current [YCRC Bouchet documentation](https://docs.ycrc.yale.edu/clusters/bouchet/). Each agent-partition job is limited to one CPU and 8 GB; check documentation for current limits. Within the session, consult local instructions and load `local-coding-agents` as documented.
3. Start your supported coding agent in this directory and give it: `Read AGENTS.md, AGENT_INSTRUCTIONS.md, and the complete RESEARCH_BRIEF.md. Derive and validate a bounded policy, initialize only if safe, then execute the documented research loop autonomously. Do not start a real campaign unless the brief is complete and authorizes it.`
4. Use `bin/autoresearch status`, `bin/autoresearch stop`, and `bin/autoresearch report` to inspect/control.

## Testing

Run the suite with `python3 -m pytest tests/`. It is stdlib/pytest only and offline:

- `tests/test_smoke.py` — the offline mechanics demo runs and exits 0.
- `tests/test_lifecycle.py` — drives a full human-brief campaign against an isolated
  copy of the template (never the working tree): incomplete/placeholder briefs and
  invalid policies are rejected with clean errors; `init` produces the campaign
  artifacts; `status`/`report`/`stop` behave; editing the brief after `init` is
  blocked; and every `research-job` guard rail fires (local-unauthorized,
  no-allocation, Slurm fail-closed). Real local execution is exercised only when the
  tests themselves run inside an active Slurm allocation.

## Resource and safety rules

For computational work inside the existing allocation, verify resources fit the allocation. Additional Slurm jobs, GPU, other partitions, network, paid services, external paths, or extra concurrency require explicit brief authorization. Validate partition/account/QoS/reservation and CPU/GPU/memory/time/concurrency/budget before submission. If required scheduler details are absent, stop with a blocker. Do not experiment on login nodes. The Slurm session script is illustrative only; site settings must be checked. Slurm unavailable means real execution stops; smoke remains offline.

The full loop and artifact expectations are in `AGENT_INSTRUCTIONS.md`. At campaign initialization preserve a brief snapshot/hash, policy provenance, assumptions, protocol, lifecycle state and unique ID. Each trial gets an isolated directory, proposal, manifest, logs, result and analysis. Record failed and inconclusive outcomes. Compare only compatible protocols; include uncertainty for noisy results. Track requested versus observed usage. A safe stop prevents new work and does not cancel active jobs by default. Keep the old campaign when changing the brief; create a new campaign explicitly.

## Limitations

This starter deliberately does not parse natural language into permissions or submit Slurm jobs automatically: its current deterministic helper rejects those operations rather than risk accidental access. A live agent must implement/validate explicit policy and cluster-specific scheduler details before real work; until that exists, use only the offline smoke. Initialize/recovery locking, full accounting, budget enforcement, and durable campaign ledger are not yet implemented. Never treat this template as proof that resource limits are enforced. Do not launch a real campaign during template setup.
