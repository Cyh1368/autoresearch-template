# The Reviewer-Researcher Loop

This is a resource-efficient auto-research template for computational research.

You need:

- a rough research idea. Chat with strong LLMs until you find it satisfactory.
- a agent coding harness
- a computing environment for the cheap model (to, for example, submit Slurm jobs)
- a cheap model (like Qwen 3.8) responsible for working on the research problem for hours
- an expensive model (GPT-6 Astra) responsible for generating the initial research proposal and the reviews. 

### Initial Research Proposal

This LLM should operate *outside* this repository. Ideally, this is the same LLM that you used to come up with the satisfactory research idea.

```
Research direction:
[INSERT IDEA OR QUESTION]

Available resources and explicit permissions:
[INSERT COMPUTE, TIME, STORAGE, NETWORK, DATA, AND OTHER AUTHORIZATIONS]

Existing assets and relevant work:
[INSERT AVAILABLE PAPERS, CODE, DATA, MODELS, AND PRELIMINARY RESULTS]

You are designing a research campaign for a capable autonomous coding agent.
Your output will be its research brief. The agent can implement experiments,
analyze results, and adapt its approach, but your brief must give it a strong
scientific starting point.

Generate your brief as a markdown document named RESEARCH_BRIEF.md.

Write a focused, executable research brief that helps the agent discover something
consequential and defensible efficiently. Do not optimize for an impressive-sounding
proposal or assume the original idea will succeed.

Before writing, investigate the closest relevant work using primary sources where
access is available. Verify that proposed models, datasets, and software exist and
support the required experiment. Distinguish verified facts, assumptions, and open
questions. Never invent citations or resource availability. If browsing is
unavailable, mark literature and feasibility claims that require verification.

The brief must establish the following:

1. A consequential question
Explain who would use the result and what scientific or practical decision it
would change. Identify the precise gap left by the closest existing approaches.
Distinguish a new mechanism, a useful method, and an informative empirical boundary.
State what would remain valuable if the proposed method fails.

2. A falsifiable starting hypothesis
Describe the proposed mechanism and at least one credible competing explanation.
Separate the phenomenon to understand from the particular method initially
suggested. Give the agent freedom to abandon that method while preserving the
central research question.

3. A minimal, discriminating first experiment
Specify the smallest experiment that can establish whether the question has
meaningful signal and the proposed approach has headroom.
Explain what different outcomes would imply and what decision each would trigger.
Where an oracle or privileged-information diagnostic is useful, specify exactly
what it reveals and what it cannot establish. Do not confuse oracle feasibility
with an implementable solution.

4. A credible experimental design
Name the reference and strongest relevant simple baselines, explaining their roles.
Define what information each method may access and when it becomes available.
Identify the independent experimental unit.
Vary the factors needed to distinguish the competing explanations independently.
Include positive controls, negative controls, irrelevant interventions, and
preservation checks where appropriate.
Require verification that the reference can solve the task and that the workload
can distinguish success from failure before interpreting method comparisons.

5. Evaluation tied to the claim
Specify primary outcomes and meaningful quality–cost comparisons.
Keep correctness, agreement with a reference, internal-state similarity, and
practical usefulness separate when they are different.
For efficiency claims, require actual end-to-end measurement and account for
setup, retained information, data movement, and other material overhead.
Identify implementation checks needed to trust the measurements.

6. Development and confirmation
Describe which decisions may be tuned on development data.
Reserve confirmation that challenges the method's assumptions: held-out structures,
conditions, workloads, or systems, rather than merely additional random examples.
Set practical thresholds using development evidence before confirmation is exposed.
Require uncertainty at the true replication unit.
Do not prescribe arbitrary sample sizes or statistical procedures without a reason.

7. An economical research sequence
Organize the campaign into a few conditional stages:
measurement validation → baseline/headroom → minimal method or diagnostic →
confirmation.
Give promotion, pivot, and stop conditions.
Prefer cheap experiments that eliminate explanations before large sweeps.
Introduce additional models, scale, and complex methods only when they resolve an
important uncertainty.
A rigorous negative finding is an acceptable endpoint.

8. Operational boundaries
Repeat only permissions actually supplied by the human.
Separate authorized ceilings from recommended working budgets.
Flag missing or contradictory authorizations explicitly; do not resolve them by
granting access.
Allow autonomous scientific decisions within the authorized envelope.

9. Evidence and reporting
Require pinned inputs and software, exact commands, per-item results, failed trials,
protocol amendments, and claim-to-evidence traceability.
Require the final account to identify the simplest competitive baseline, failure
regimes, unsupported claims, and the practical decision supported by the evidence.

Write the final brief in these sections:
Research question; Intended contribution and closest work; Experimental setting;
First diagnostic; Baselines and controls; Evaluation and confirmation;
Conditional research sequence; Resources and permissions; Limitations;
Evidence and reporting.

Be concrete about the scientific distinctions that matter. Leave implementation
choices to the coding agent unless they are essential to validity.
Do not create an exhaustive benchmark suite or a rigid experiment list.
End with the first experiment and the decision it is intended to resolve.
```

### Autoresearch Agent Initial Prompt

Clone this template, replace RESEARCH_BRIEF.md with what the external LLM generated, and start the auto-research with the prompt below. 

```
Read AGENTS.md, AGENT_INSTRUCTIONS.md, and the complete RESEARCH_BRIEF.md. Derive and validate a bounded policy, initialize only if safe, then execute the documented research loop autonomously. Do not start a real campaign unless the brief is complete and authorizes it. Save your final paper in /documents,
```

### Review agent prompt

Run this with the expensive model having access to the manuscript generated by the auto-research agent.

```
You are a demanding, constructive research reviewer advising an autonomous research
agent. Your review should help the agent reach a more important and defensible
result with less wasted work.

You receive the manuscript and, when one was written for this version, the author's
response to the previous review. Experimental data, code, logs, and campaign records
are withheld. Judge the manuscript by what it reports. Ask for missing evidence to
be written into the manuscript.

Decide whether to accept or reject the work on quality, clarity, significance, and
originality. Score each of those four on a 4-point scale (4 excellent, 3 good,
2 fair, 1 poor). Give an overall recommendation from 6 Strong Accept through
5 Accept, 4 Borderline Accept, 3 Borderline Reject, 2 Reject, and 1 Strong Reject.

On accept, the remark recommends the journals or conferences that fit the work.
The supervisor saves it as documents/REMARK.md. On reject, the supervisor saves
the review as documents/REVIEW.md.

Evaluate the work actually supported by the manuscript. State what you
inspected and what remains unaudited. Do not treat a manuscript's description of
an experiment as independent verification that it ran correctly.

Identify the most consequential unresolved questions and propose
experiments that discriminate between answers. Do not simply request more data,
more models, or more benchmarks.

Assess:

1. Contribution
What is the strongest potentially important finding? How does it differ from the
closest prior work? Is the contribution a method, mechanism, empirical boundary,
measurement correction, or useful negative result?

Verify consequential novelty claims against primary sources when possible.
Do not mistake a new combination of familiar components for demonstrated impact.

2. Validity
For each central conclusion, consider:
- an implementation or scoring artifact;
- a workload confound;
- a simpler explanation;
- privileged information unavailable to a feasible method;
- an unfair or weak baseline;
- selection, leakage, or dependence among observations.

Identify which alternatives remain plausible. Distinguish an observed association
from a mechanism established by intervention.

3. Measurement and inference
Check task validity, reference performance, endpoint definitions, independent sample
counts, pairing, clustering, selection, and uncertainty.

Matching accuracy does not establish matching distributions. A nonsignificant
difference does not establish equivalence. A numerical diagnostic does not by
itself establish behavioral importance.

Question claims of exactness, generality, and constant cost. Ask for checks targeted
to the execution paths and regimes supporting those claims.

4. Operational value
Does the method have access only to permitted information at decision time?
Does its benefit survive realistic selection, preprocessing, state construction,
metadata, transfer, and fallback costs?

Distinguish oracle demonstrations, feasible implementations, proxy savings, and
measured end-to-end improvements.

5. Generalization and scope
Which claims survive across the tested conditions? Which depend on model, scale,
task structure, workload, or numerical implementation?

Check whether confirmation meaningfully challenges the explanation, rather than
repeating the development setting.

If you decide to reject and write a review, it should include

A. Give a concise assessment and name the strongest supported contribution.

B. Rank a small number of major issues by how much they threaten validity or value.
For each issue provide:
- the exact claim at risk;
- the evidence or ambiguity causing concern;
- at least one competing explanation;
- the smallest discriminating experiment or reanalysis;
- what outcomes would support, narrow, or reject the claim.

C. Propose a prioritized research program.
Separate:
- corrections required before existing results can be trusted;
- decisive experiments required for the central contribution;
- optional extensions.

Respect the remaining budget. Where possible, use existing per-item results before
requesting new computation. Prefer orthogonal interventions and matched comparisons
over broad sweeps.

D. State branch-specific stop and pivot conditions.
If an oracle diagnostic shows insufficient headroom, say which method-development
branch should close. If a claimed mechanism fails, identify whether a narrower
empirical result remains valuable.

E. Describe the strongest claim the study could responsibly make now, and what
additional evidence would justify a stronger claim.

If reviewing an early pilot, emphasize measurement validity, headroom, and experiment
choice. If reviewing a mature manuscript, additionally audit literature positioning,
statistical language, operational value, and consistency across abstract, tables,
and limitations.

Do not prescribe favorable outcomes. Do not require every suggested experiment.
Do not claim the work is publishable merely because a checklist is completed.
Make the review scientifically specific enough that the agent can act without
asking you to design the experiments again.
```

### Autoresearch Agent Continuation

```
Continue the existing research campaign using the newest review in /documents.

Your objective is to resolve the review's most consequential scientific uncertainties
and produce the strongest auditable result the evidence supports within the remaining
authorized resources. A useful negative result or a narrowed contribution is an
acceptable outcome.

First read the repository's operating instructions, complete research brief, review,
current protocol, findings, experiment ledger, resource policy, budget, and handoff.
Recover and reconcile active jobs before submitting anything. Do not initialize a
new campaign, duplicate jobs, or expand permissions merely because this prompt asks
you to continue.

Then proceed autonomously:

1. Turn the review into a research decision plan
For each major issue, record:
- the claim being challenged;
- what the reviewer believes is missing;
- whether existing evidence resolves it;
- the smallest additional analysis or experiment needed;
- competing predictions;
- the decision that each outcome would trigger.

Distinguish measurement defects from scientific uncertainty and presentation issues.
Fix defects that undermine interpretation before collecting more results.

Do not accept every reviewer assertion automatically. Check it against the evidence.
If you disagree, document a precise, supported response.

2. Prioritize the decisive work
Identify the central contribution worth preserving or testing. Rank proposed work by
its ability to change the scientific conclusion relative to cost and effort.

Run cheap reanalyses and falsification tests before expensive extensions. Avoid
developing a complicated method when a diagnostic can first determine whether it
has enough headroom.

Use the review as scientific guidance, not as an obligation to execute every suggested
experiment or to reproduce the reviewer's preferred explanation.

3. Freeze the relevant decisions before scoring
For each new experiment, record the hypothesis, changed and fixed factors, baselines,
information available to each arm, primary endpoints, replication unit, analysis,
practical tolerances, inclusion rules, and branch decision criteria.

Use development measurements to calibrate choices where necessary. Freeze them before
opening confirmation results. Record amendments, failed runs, and exposure to held-out
data. Never silently replace an unsuccessful endpoint or redefine success.

4. Validate the measurement pipeline
Run a small end-to-end check before large jobs. Confirm that the task is informative,
the reference behaves as expected, scoring matches the intended endpoint, state is
isolated across measurements, and numerical paths satisfy any claimed tolerances.

Investigate surprising results with targeted controls. Preserve failed and invalid
runs, label their status, and identify which conclusions they invalidate.

5. Execute, analyze, and adapt
Use the authorized execution workflow and record commands, versions, hashes, inputs,
seeds, job identities, raw measurements, and resource usage.

Analyze paired outcomes and uncertainty at the correct independent unit. Report all
relevant strata, including failed capability or headroom gates. Clearly distinguish
exploration from confirmation and oracle interventions from feasible methods.

After each decisive result, update the research plan:
- continue if the prerequisite evidence supports the next stage;
- narrow or revise the explanation if alternatives survive;
- close a branch when its stopping rule is met;
- confirm an informative negative result when that is the best use of the budget.

Do not repeatedly run variants simply to obtain a positive result.

6. Test practical value and generalization
For a surviving method, evaluate the real decision-time inputs and full operational
cost against strong baselines. Report quality–cost tradeoffs and fallback behavior.

Use confirmation that challenges the proposed explanation. Scope conclusions to the
systems, tasks, scales, and conditions actually tested.

7. Keep conclusions synchronized with evidence
Maintain a claim-to-evidence record and explicitly mark claims that are confirmed,
narrowed, withdrawn, or unresolved.

Update current summaries so superseded findings do not remain presented as established
results. Preserve the historical record. Ensure the abstract, tables, discussion,
and reviewer response describe the same endpoints and supported scope.

8. Finish with an evidence-based handoff
Produce a response organized by the review's major issues:
- what changed;
- which evidence addresses the concern;
- what conclusion is now justified;
- what remains unresolved and why.

Include the strongest supported contribution, important negative results, limitations,
artifact locations, remaining budget, and active-job status.

Make routine scientific and engineering decisions yourself and document them.
Do not ask the user to choose ranks, baselines, analyses, or the next experiment when
the available evidence supports a reasonable choice.

If a necessary action lacks authorization, record the precise blocker and continue
independent authorized work where possible. Never reinterpret scientific autonomy
as permission to obtain new resources.

Continue until the decisive research program is resolved, a legitimate blocker
prevents further useful progress, or the authorized budget/allocation ends. Do not
continue indefinitely in pursuit of a promised “publishable” outcome.
```

## How it works

The system splits responsibility between a human brief, the live coding agent (the
controller), and a small deterministic, stdlib-only helper (`core/runner.py` behind
`bin/autoresearch` and `bin/research-job`). The helper never interprets prose into
permissions and never submits cluster jobs on its own — it only enforces the fields
that were explicitly recorded in a policy file and refuses anything else.
`bin/autoresearch loop` is the outer supervisor: it runs the controller once per
manuscript version, sends only that manuscript to a strong model, and syncs git.

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

## Autonomous review loop

The human writes `RESEARCH_BRIEF.md` and starts `bin/autoresearch loop`. That is the
per-campaign intervention. The supervisor then repeats:

1. `git pull` when `origin` has an upstream.
2. Run the configured research agent on `loop/prompts/agent_initial.md` or
   `loop/prompts/agent_continue.md`. Any agent command works. The template does not
   assume a cluster, an account, or a product.
3. When the agent exits, read `documents/paper.md` and, if it is new,
   `documents/response.md`. Snapshot that pair under `documents/versions/`.
4. Call the strong model with `loop/prompts/review.md` and those texts. Code, logs,
   datasets, campaign records, and other files under `documents/` are not attached.
5. Commit and `git push`. API keys, `.env`, and diffs that contain key material are
   left unstaged.
6. Stop when the review decision is `accept`.
7. Otherwise, once three versions exist, call the same model with
   `loop/prompts/progress.md` and the last three manuscripts. Stop when that call
   reports no significant progress. A positive progress judgment starts another
   agent version.

Exit codes: `0` accepted or paused by `--max-cycles`, `3` no significant progress,
`2` blocked. Accepted and stalled loops stay stopped until `documents/loop-state.json`
is removed together with `documents/versions/`. A blocked loop retries on the next
`bin/autoresearch loop`.

The default strong model is OpenRouter `openai/gpt-6-sol` (GPT-6 Sol), using
`OPENROUTER_API_KEY`. `loop.config.json` can switch provider, model, base URL, and
key variable. Presets: `openrouter`, `openai`, `anthropic`, `gemini`, and
`openai-compatible`. Copy `loop.config.example.json`. Put the key in the environment
named by `api_key_env`. A key inside the config file is rejected.

`bin/autoresearch usage` prints the local ledger at `usage/api-usage.jsonl`
(call, model, prompt tokens, completion tokens, reported cost, redacted key hint).
`--live` also queries the provider key endpoint when it has one. OpenRouter's
`GET /api/v1/key` supplies usage, limit, and remaining credit. The raw key is not
written to the ledger, the review, or git.

`bin/autoresearch review` sends the current manuscript once and does not advance
the stop state. Use `loop` for the unattended cycle.

### Commands

These are optional to use.

| Command | Effect |
| --- | --- |
| `bin/autoresearch check` | Report Python version and whether `sbatch`/`squeue` are available. |
| `bin/autoresearch init` | Validate the brief and `./policy.json`, then create `campaign/<id>/`. |
| `bin/autoresearch start` | Print a reminder that the foreground agent runs the loop. |
| `bin/autoresearch status` | Print the current campaign's state and policy as JSON (verifies brief hash). |
| `bin/autoresearch report` | Write `report.md` (status + experiment count) for the current campaign. |
| `bin/autoresearch stop` | Request a graceful stop (drops `STOP`; does not cancel jobs). |
| `bin/autoresearch smoke` | Run the offline mechanics demo in `examples/smoke_test/`. |
| `bin/autoresearch loop` | Run the agent, review the manuscript, sync git, and stop on accept or a stalled window. |
| `bin/autoresearch usage` | Print local token spend and, with `--live`, the provider key's usage. |
| `bin/autoresearch review` | Send the current manuscript to the strong model once. |
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
- `loop/` — supervisor, provider wires, prompts, and usage ledger writer.
- `loop.config.example.json` — provider, agent command, git remote, and the three-version stop.
- `usage/api-usage.jsonl` — created on the first strong-model call. Safe to commit: key hints only.

## Quick start

1. Copy this directory and edit `RESEARCH_BRIEF.md`. That file is the only per-campaign human input.
2. Export a strong-model key. The default provider is OpenRouter and the default model is `openai/gpt-6-sol` (GPT-6 Sol): `export OPENROUTER_API_KEY=...`. Other providers, base URLs, and models go in `loop.config.json`. See `loop.config.example.json`.
3. Export the research-agent command once. `{prompt_file}` is replaced with the handoff prompt. The process must write `documents/paper.md` and exit: `export AUTORESEARCH_AGENT_COMMAND='your-agent --prompt-file {prompt_file}'`.
4. Start the unattended loop with `bin/autoresearch loop`, then inspect spend with `bin/autoresearch usage`.

### Example: Yale Bouchet

Obtain a Bouchet agent-partition session under current [YCRC Bouchet documentation](https://docs.ycrc.yale.edu/clusters/bouchet/). Each agent-partition job is limited to one CPU and 8 GB; check documentation for current limits. Within the session, consult local instructions and load `local-coding-agents` as documented. Point `AUTORESEARCH_AGENT_COMMAND` at the coding agent in that session. Separate Slurm submissions stay fail-closed until the brief authorizes them. `bin/autoresearch status`, `stop`, and `report` still inspect the campaign.

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
- `tests/test_loop.py` — the supervisor, with a fake agent and a fake HTTP transport:
  OpenRouter/GPT-6 Sol defaults, manuscript-only requests, accept and stall stops,
  usage redaction, provider wires, and git refusal of `.env` and key material.

## Resource and safety rules

For computational work inside the existing allocation, verify resources fit the allocation. Additional Slurm jobs, GPU, other partitions, network, paid services, external paths, or extra concurrency require explicit brief authorization. Validate partition/account/QoS/reservation and CPU/GPU/memory/time/concurrency/budget before submission. If required scheduler details are absent, stop with a blocker. Do not experiment on login nodes. The Slurm session script is illustrative only; site settings must be checked. Slurm unavailable means real execution stops; smoke remains offline.

The full loop and artifact expectations are in `AGENT_INSTRUCTIONS.md`. At campaign initialization preserve a brief snapshot/hash, policy provenance, assumptions, protocol, lifecycle state and unique ID. Each trial gets an isolated directory, proposal, manifest, logs, result and analysis. Record failed and inconclusive outcomes. Compare only compatible protocols; include uncertainty for noisy results. Track requested versus observed usage. A safe stop prevents new work and does not cancel active jobs by default. Keep the old campaign when changing the brief; create a new campaign explicitly.

## Limitations

This starter deliberately does not parse natural language into permissions or submit Slurm jobs automatically: its current deterministic helper rejects those operations rather than risk accidental access. The outer loop does call the configured strong model, and only with the manuscript and author response. A live agent must implement/validate explicit policy and cluster-specific scheduler details before real compute; until that exists, use only the offline smoke for experiments. Initialize/recovery locking, full accounting, budget enforcement, and durable campaign ledger are not yet implemented. Never treat this template as proof that resource limits are enforced. Do not launch a real campaign during template setup. The strong-model calls spend the configured API key; `bin/autoresearch usage` is the record of that spend.
