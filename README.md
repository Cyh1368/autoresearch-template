# The reviewer-researcher loop

This is a template for a computational research campaign. You write `RESEARCH_BRIEF.md`. A coding agent runs the experiments and writes a manuscript. A strong model reviews that manuscript. `bin/autoresearch loop` repeats the cycle, syncs git, and stops on its own.

The brief is the only per-campaign input. The API key and the agent command are one-time setup. The default reviewer is OpenRouter model `openai/gpt-6-sol` (GPT-6 Sol). The research agent is whatever command you configure.

Two programs share the repository:

- `bin/autoresearch loop` is the supervisor. It runs the agent once per manuscript version, calls the strong model, and pushes.
- `core/runner.py`, behind `bin/autoresearch` and `bin/research-job`, is the campaign helper the agent uses inside a version. It records policy and refuses unsanctioned execution. It does not call the strong model.

## Quick start

1. Copy this directory and fill in `RESEARCH_BRIEF.md`. Sections 1, 3, 4, and 7 are required. Section 4 is where permissions live. `bin/autoresearch init` refuses a brief that still contains `[Question`, `[Systems`, or `[Scope`.
2. Export the reviewer key. The default provider is OpenRouter:

```sh
export OPENROUTER_API_KEY=...
```

3. Export the research-agent command. `{prompt_file}` becomes the handoff prompt. The process writes `documents/paper.md` and exits:

```sh
export AUTORESEARCH_AGENT_COMMAND='your-agent --prompt-file {prompt_file}'
```

4. Start the loop, then inspect spend:

```sh
bin/autoresearch loop
bin/autoresearch usage
```

Copy `loop.config.example.json` to `loop.config.json` to set the provider, model, base URL, agent argv, git remote, or stop window. A key, token, or secret written inside the config file is rejected. `AUTORESEARCH_API_KEY` overrides the named key variable for one shell.

## One cycle

```
RESEARCH_BRIEF.md
        |
        v
git pull, when origin has an upstream
        |
        v
research agent, one version, then exit
        |  writes documents/paper.md
        |  after a review, also writes a new documents/response.md
        |  keeps experiments in campaign/<id>/
        v
strong model reviews the manuscript
        |
        v
git commit and git push
        |
        +-- accept --> stop
        |
        +-- revise, and three versions exist
                |
                v
            progress check on the last three manuscripts
                |
                +-- no significant progress --> stop
                +-- progress --> next agent version
```

The pull is `git pull --rebase --autostash` on the current branch. With no upstream, the supervisor skips the pull and still commits and pushes.

The first version receives `loop/prompts/agent_initial.md`. Later versions receive `loop/prompts/agent_continue.md`, including the latest review. The rendered prompt is written to `documents/handoff/prompt.md`. Placeholders in the agent command are `{prompt_file}`, `{prompt}`, and `{repo}`.

When the agent exits, the supervisor reads `documents/paper.md`. It also reads `documents/response.md` when that file is new. An unchanged response is withheld. Both texts are copied to `documents/versions/vNNN/` with `manifest.json`. The manifest lists the attached texts and sets `experimental_data_attached` to false. Code, logs, datasets, campaign records, and other documents are left out of the request.

The review uses `loop/prompts/review.md`. After a revise decision, once `stop.stale_window` versions exist (default 3), the same cycle calls `loop/prompts/progress.md` on that window. The progress call sees those manuscripts, the author responses that were sent with them, and the reviews. It does not see the campaign directory.

The agent finishes one version and exits. The supervisor calls the model and runs git. Leave `git push`, `git pull`, and `git reset` to the supervisor.

If the agent exits without a new manuscript, the supervisor runs it once more and then blocks. It does not call the model for that attempt.

## When the loop stops

The review scores quality, clarity, significance, and originality from 4 (excellent) to 1 (poor), and gives an overall recommendation from 6 (Strong Accept) to 1 (Strong Reject). The prompt accepts only recommendation 5 or 6. Every other recommendation is stored as `revise`, so a rejected paper continues until the progress check stops it. A useful negative result or a narrowed claim can be accepted when the manuscript stands on its own.

Significant progress is a material change in the claim, the evidence, the scope, or the validity of the argument. A narrowing, a withdrawn claim, or a negative result counts when it would change what a careful reader believes. Rewording the same result does not. When the manuscripts are too thin to judge, the progress prompt tells the model to report progress and name the gap.

| Status | Exit | Meaning |
| --- | --- | --- |
| `accepted` | 0 | The review decision was accept. |
| `running` | 0 | Paused by `--max-cycles`. The status stays `running`. |
| `stalled` | 3 | The progress check reported no significant progress. |
| `blocked` | 2 | The brief changed, git failed, the agent wrote no paper, the provider rejected the call, the reply was unusable, or another loop holds the lock. |

`--max-cycles N`, or `stop.max_cycles` in the config, pauses after N cycles in this process. The next `bin/autoresearch loop` continues. A second loop in the same checkout blocks on `documents/.loop.lock`.

Accepted and stalled loops stay stopped until `documents/loop-state.json` and `documents/versions/` are removed together. The supervisor refuses to overwrite an existing version directory.

A blocked loop clears that flag on the next run and retries. If a snapshot was saved and the decision is empty, the retry reviews that snapshot and does not run the agent. If the version record already says accept or stall, the retry pushes that result and does not start another agent run.

The first cycle pins the SHA-256 of `RESEARCH_BRIEF.md`. A later edit blocks the loop. Keep that state, and start a new loop if the brief should change.

Provider HTTP 400, 401, 403, and 404 block immediately. Other provider errors, and a reply that is not the expected JSON, are tried once more and then block. Both the failure and the successful call are appended to the usage ledger.

`bin/autoresearch review` sends the current manuscript once. It writes `documents/reviews/adhoc.md` and updates `documents/REMARK.md` or `documents/REVIEW.md`. It does not move the stop state and does not create `v000`.

## Files the review leaves behind

Accept writes `documents/REMARK.md` and removes `documents/REVIEW.md`. Revise writes `documents/REVIEW.md` and removes `documents/REMARK.md`. The remark names the four scores, the recommendation, and fitting journals or conferences. The review names the supported contribution, the issues that threaten it, required corrections versus optional work, what should stop if the next result fails, and the strongest claim the study can make now.

Each loop review is also stored as `documents/reviews/vNNN.md` and `documents/reviews/vNNN.json`. Each progress judgment is stored as `documents/progress/vNNN.json`.

The instructions the supervisor sends are `loop/prompts/review.md`, `loop/prompts/progress.md`, `loop/prompts/agent_initial.md`, and `loop/prompts/agent_continue.md`. Edit those files to change the next call.

## Configuration

Settings resolve in this order: built-in defaults, the provider preset, fields in the config file that belong to the selected provider, then environment variables. `AUTORESEARCH_LOOP_CONFIG` selects a file. Otherwise the supervisor reads `loop.config.json` when that file exists.

`AUTORESEARCH_PROVIDER` can switch provider. A switch keeps `model`, `timeout_seconds`, and `max_tokens` from the file, and takes the new preset's base URL and key variable. `AUTORESEARCH_MODEL`, `AUTORESEARCH_BASE_URL`, and `AUTORESEARCH_API_KEY_ENV` apply after that. Anthropic, Gemini, and Azure reject the OpenRouter slug `openai/gpt-6-sol` until you set a model for that provider. `openai-compatible` has no default URL or key variable: set `base_url`, `model`, and `api_key_env`.

`azure` reads the resource URL from `AZURE_ENDPOINT` and the key from `AZURE_API_KEY`. A resource URL such as `https://YOUR-RESOURCE.openai.azure.com` is called at `https://YOUR-RESOURCE.openai.azure.com/openai/v1/chat/completions`. An endpoint that already ends in `/openai/v1` is used as given. `strong_model.model` or `AUTORESEARCH_MODEL` is the Azure deployment name. The request sends that key in the `api-key` header. `AUTORESEARCH_BASE_URL` still overrides `AZURE_ENDPOINT` when both are set.

| Provider | Request | Key variable | Live key usage |
| --- | --- | --- | --- |
| `openrouter` | OpenAI chat completions at `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | `GET {base}/key` |
| `openai` | OpenAI chat completions | `OPENAI_API_KEY` | local ledger only |
| `anthropic` | `POST /v1/messages`, header `anthropic-version: 2023-06-01` | `ANTHROPIC_API_KEY` | local ledger only |
| `gemini` | `generateContent` | `GEMINI_API_KEY` | local ledger only |
| `azure` | OpenAI chat completions at `{AZURE_ENDPOINT}/openai/v1`, header `api-key` | `AZURE_API_KEY` | local ledger only |
| `openai-compatible` | OpenAI chat completions at your `base_url` | the variable you name | set `key_usage_path` to enable |

The OpenRouter call sends `X-Title: autoresearch-template`. The model timeout defaults to 900 seconds. `max_tokens` is omitted for OpenAI-compatible calls unless you set it. Anthropic always sends `max_tokens`, and uses 16000 when you leave it unset.

`agent.prompt_via` is `file` (the command must contain `{prompt_file}`), `argv` (the command must contain `{prompt}` or `{prompt_file}`), or `stdin`. `agent.timeout_minutes` bounds one agent run. `git.enabled` defaults to true and `git.remote` defaults to `origin`. Set `git.enabled` to false to run with no pull or push.

Environment variables:

| Variable | Effect |
| --- | --- |
| `OPENROUTER_API_KEY` | Default reviewer key. |
| `AUTORESEARCH_API_KEY` | Used instead of the named key variable. |
| `AUTORESEARCH_PROVIDER` | `openrouter`, `openai`, `anthropic`, `gemini`, `azure`, or `openai-compatible`. |
| `AZURE_ENDPOINT` | Azure resource URL when the provider is `azure`. |
| `AZURE_API_KEY` | Azure key. Used when the provider is `azure`. |
| `AUTORESEARCH_MODEL` | Model id. |
| `AUTORESEARCH_BASE_URL` | API base URL. |
| `AUTORESEARCH_API_KEY_ENV` | Name of the environment variable that holds the key. |
| `AUTORESEARCH_AGENT_COMMAND` | Research-agent argv. Overrides `agent.argv`. |
| `AUTORESEARCH_PROMPT_VIA` | `file`, `argv`, or `stdin`. |
| `AUTORESEARCH_LOOP_CONFIG` | Path to the JSON config. |

## API usage

`bin/autoresearch usage` prints the provider, model, base URL, and a redacted key hint (the variable name and the last four characters). It then sums `usage/api-usage.jsonl`: calls, prompt tokens, completion tokens, and the cost the provider reported. Each line records the time, operation (`review` or `progress`), version, status, and request id. The raw key is not written to the ledger, the review, or git.

`--live` is the default. On OpenRouter it queries `GET /api/v1/key` and prints usage, daily, weekly, and monthly figures, the limit and remaining credit, bring-your-own-key usage, and the effective budget when the provider returns them. Providers without a key endpoint print the local ledger and say so. A failed live query is reported and does not fail the command. `--no-live` skips the network.

## Git

With git enabled, each reviewed version is committed with `git add -A` and pushed with `git push -u <remote> HEAD`. Paths matching `.env`, `.pem`, `.key`, `id_rsa`, `credentials.json`, or a service-account file are unstaged. A staged diff that matches an API-key pattern is unstaged and the loop blocks. Campaign directories are gitignored, so experiment logs stay local. Manuscripts, reviews, `documents/loop-state.json`, and `usage/api-usage.jsonl` are part of the commit.

The supervisor does not rewrite history. A detached `HEAD` blocks the sync. A repository with no `origin` remote is committed locally.

## The research campaign

Inside a version, the agent follows `AGENT_INSTRUCTIONS.md`. It reads the brief, writes `./policy.json` with exactly these keys, and runs `bin/autoresearch init` from the repository root:

`allow_local`, `allow_slurm`, `partitions`, `cpus_max`, `memory_mb_max`, `gpus_max`, `wall_minutes_max`, `concurrency_max`, `attempts_max`, `elapsed_hours_max`, `storage_mb_max`.

`init` checks that those keys are present and well formed. Booleans must be booleans, the numeric caps must be nonnegative, `allow_slurm` requires a non-empty `partitions` list, and at least one of local or Slurm must be authorized. The helper does not enforce the numeric caps at runtime. The agent stays inside the brief.

`init` snapshots the brief into `campaign/<timestamp>-<id>/` and stores its SHA-256. A later edit makes `status` and `report` stop with "brief changed". Keep the old campaign and initialize a new one. `current()` is the lexicographically latest campaign directory that contains `state.json`. `init` reads `./policy.json` from the current working directory, so run it from the repository root. `loop`, `usage`, and `review` locate the repository from the `bin/autoresearch` script, independent of the shell's working directory.

Experiments go through `bin/research-job`:

- `local` runs the command when the policy sets `allow_local` and `SLURM_JOB_ID` is set. Without an allocation it refuses.
- `slurm` refuses. The helper accepts a validated policy and does not submit a site job.
- `bin/autoresearch smoke` is the offline mechanics demo. It is the only execution path that runs with no allocation.

`bin/autoresearch stop` creates `campaign/<id>/STOP` and does not cancel running jobs. `start` prints a reminder that the foreground agent runs the campaign loop. Its exit ends that version. The supervisor then reviews whatever manuscript the agent wrote.

## Commands

| Command | Effect |
| --- | --- |
| `bin/autoresearch check` | Print the Python version and whether `sbatch` and `squeue` are on `PATH`. |
| `bin/autoresearch init` | Validate the brief and `./policy.json`, then create `campaign/<id>/`. |
| `bin/autoresearch start` | Print the reminder that the foreground agent runs the campaign. |
| `bin/autoresearch status` | Print the current campaign's state and policy as JSON. Checks the brief hash. |
| `bin/autoresearch report` | Write `report.md` for the current campaign. |
| `bin/autoresearch stop` | Request a graceful stop. Drops `STOP`. Does not cancel jobs. |
| `bin/autoresearch smoke` | Run `examples/smoke_test/`. |
| `bin/autoresearch loop` | Run agent versions, review them, sync git, and stop on accept or a stalled window. |
| `bin/autoresearch loop --max-cycles N` | Stop this process after N cycles. Status stays `running`. |
| `bin/autoresearch usage` | Print the local ledger and, by default, live key usage. |
| `bin/autoresearch usage --no-live` | Print the local ledger only. |
| `bin/autoresearch review` | Send the current manuscript to the strong model once. |
| `bin/research-job local POLICY.json COMMAND...` | Run a command inside an active Slurm allocation when the policy allows it. |
| `bin/research-job slurm POLICY.json COMMAND...` | Refuses. |

## Layout

- `RESEARCH_BRIEF.md`: the human-edited brief.
- `AGENT_INSTRUCTIONS.md`: the protocol the research agent follows during a version.
- `core/runner.py`: campaign state and the experiment gate. Stdlib only.
- `bin/autoresearch`, `bin/research-job`: command entry points.
- `loop/`: supervisor, provider clients, prompts, and the usage-ledger writer.
- `loop/prompts/`: review, progress, and agent prompts.
- `loop.config.example.json`: sample provider, agent command, git remote, and stop window.
- `documents/paper.md`, `documents/response.md`: the texts the strong model can see.
- `documents/versions/vNNN/`: snapshotted manuscript, optional response, and manifest.
- `documents/reviews/`: `vNNN.md`, `vNNN.json`, and `adhoc.md` from a one-shot review.
- `documents/REMARK.md` or `documents/REVIEW.md`: the latest accept remark or revise review.
- `documents/progress/`: progress judgments.
- `documents/loop-state.json`: status, brief hash, and per-version decisions.
- `documents/handoff/prompt.md`: the prompt given to the current agent run.
- `usage/api-usage.jsonl`: created on the first strong-model call. Key hints only.
- `campaign/<id>/`: brief snapshot, policy, state, ledger, findings, protocol, and one directory per experiment. Gitignored.
- `examples/smoke_test/`: offline demo. Output is gitignored.
- `slurm/agent-session.example.sh`: illustrative session notes.

## Example: Yale Bouchet

Obtain a Bouchet agent-partition session under the current [YCRC Bouchet documentation](https://docs.ycrc.yale.edu/clusters/bouchet/). Each agent-partition job is limited to one CPU and 8 GB. Check the documentation for current limits. Inside the session, follow the local instructions and load `local-coding-agents` as documented. Point `AUTORESEARCH_AGENT_COMMAND` at the coding agent in that session. The template does not require Bouchet. Separate Slurm submissions stay refused until a later helper can accept a site-valid job request, and until the brief authorizes them. `status`, `stop`, and `report` still inspect the campaign from that session.

## Testing

`python3 -m pytest tests/` runs offline and uses the stdlib plus pytest.

- `tests/test_smoke.py`: the offline demo exits 0.
- `tests/test_lifecycle.py`: drives a campaign against an isolated copy of the template. Incomplete briefs and invalid policies are rejected. `init`, `status`, `report`, and `stop` behave. Editing the brief after `init` is blocked. The `research-job` guards fire: local unauthorized, no allocation, and Slurm refused. Real local execution runs only when the tests themselves are inside a Slurm allocation.
- `tests/test_loop.py`: a fake agent and a fake HTTP transport cover the OpenRouter and GPT-6 Sol defaults, manuscript-only requests, accept and stall, usage redaction, the provider wires (including Azure), and git refusal of `.env` and key material.

## Resource and safety rules

For work inside the current allocation, confirm that the job fits that allocation. Further Slurm jobs, extra GPUs, other partitions, network, paid services, external paths, or extra concurrency require an explicit statement in the brief. Confirm partition, account, QoS, reservation, and the CPU, GPU, memory, time, concurrency, and budget figures before any submission. If a required scheduler value is missing, record a blocker and stop. Do not run experiments on login nodes. `slurm/agent-session.example.sh` is an illustration. Check the site before using it. If Slurm is unavailable, real execution stops. Smoke stays available offline.

At `init`, keep the brief snapshot and hash, the policy, the assumptions, the protocol, and the campaign id. Each trial gets its own directory, proposal, manifest, logs, result, and analysis. Record failed and inconclusive outcomes. Compare compatible protocols, and include uncertainty for noisy results. Track requested use against observed use. A stop file prevents new work and does not cancel active jobs. After a brief change, keep the old campaign and create a new one.

## Limitations

The campaign helper does not parse the brief into permissions, and it does not submit Slurm jobs. The supervisor does call the configured strong model, and the request is the manuscript plus a new author response. A live agent has to write `policy.json` and any site-specific scheduler details before real compute. Until that exists, use `bin/autoresearch smoke` for experiments. Initialize and recovery locking for campaigns, full accounting, numeric budget enforcement, and a durable campaign ledger are not implemented. The template is not evidence that resource caps are enforced. Do not launch a real campaign while you are only setting up the template. Strong-model calls spend the configured API key. `bin/autoresearch usage` is the record of that spend.
