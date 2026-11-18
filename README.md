# The reviewer-researcher loop

This is a template for a computational research campaign. You write `RESEARCH_BRIEF.md`, open your coding agent, and paste one prompt. The agent runs the experiments and writes the manuscript. When a version is ready, the agent runs `bin/autoresearch submit`. That command sends the manuscript to a strong model, saves the review in `documents/`, and pushes. One reviewer reads it first. If that reviewer accepts, two more reviewers must also accept before the campaign finishes. Otherwise the agent sleeps 600 seconds, reads the review, and continues in the same session.

The brief is the only per-campaign input. The reviewer API key is one-time setup. The default reviewer is OpenRouter model `openai/gpt-6-sol` (GPT-6 Sol). You choose the coding agent and drive it yourself.

Two programs share the repository:

- `bin/autoresearch submit` is the handoff. The agent calls it. It calls the strong model and pushes. It does not start the coding agent.
- `core/runner.py`, behind `bin/autoresearch` and `bin/research-job`, is the campaign helper the agent uses inside a version. It records policy and refuses unsanctioned execution. It does not call the strong model.

## Interactive session

You stay in the coding agent's terminal. The agent calls `bin/autoresearch submit` when a manuscript is ready. You do not start `bin/autoresearch loop`, and you do not set `AUTORESEARCH_AGENT_COMMAND`.

1. Fill in `RESEARCH_BRIEF.md`. Sections 1, 3, 4, and 7 are required. Section 4 is where permissions live. `bin/autoresearch init` refuses a brief that still contains `[Question`, `[Systems`, or `[Scope`. The agent runs `init` later, after it has written `policy.json`.

2. Load the reviewer key into the same shell you will use to start the agent. `submit` inherits that environment. The program does not read a `.env` file by itself.

```sh
set -a
source .env
set +a
```

For OpenRouter, `.env` contains `OPENROUTER_API_KEY`. For Azure it contains:

```
AZURE_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com
AZURE_API_KEY=your-key
AUTORESEARCH_PROVIDER=azure
AUTORESEARCH_MODEL=your-deployment-name
```

`AUTORESEARCH_MODEL` on Azure is the deployment name. On OpenRouter, GPT-6 Sol is `openai/gpt-6-sol`, which is already the default. Copy `loop.config.example.json` to `loop.config.json` when you want a provider, base URL, git remote, or stop window on disk. A key written in that file is rejected.

3. From the repository root, start the agent so its terminal stays open. With Pi:

```sh
pi
```

4. Paste the contents of `loop/prompts/interactive.md` as the first message. That prompt tells the agent to read the brief, run one version, call `bin/autoresearch submit`, sleep 600 seconds, then read the review and continue or stop.

5. Watch that same terminal. Pi prints its own steps there: files it reads, commands it runs, and the manuscript it writes. `submit` prints into that trace as well. From another shell you can follow the files it creates:

- `documents/paper.md` is the current manuscript.
- `documents/response.md` is the author's reply on later versions.
- `campaign/<id>/` is the experiment record.
- `documents/reviews/vNNN.md` is the saved review.
- `documents/REVIEW.md` is the latest request for changes. `documents/REMARK.md` is the accept note. Only one of those two is kept.
- `documents/loop-state.json` is the stop state.

6. When the agent decides the version is written, it runs `bin/autoresearch submit` and waits. That command pulls, sends the manuscript to one reviewer, and, only if that reviewer accepts, sends it to two more. It writes the review, commits, and pushes. It returns when the files are on disk. The agent then runs `sleep 600` and reads the file named in the command's last lines.

7. Read the end of the `submit` output.

- `Sleep 600 seconds, then read documents/REVIEW.md and continue.` The review asked for changes. After the sleep the agent writes the next version in the same session, including a new `documents/response.md`.
- `Read documents/REMARK.md and stop.` All three reviewers accepted. The session is finished.
- `This campaign is stalled. Stop.` The last three versions did not make significant progress. The session is finished.
- `A person has to clear this block.` The command failed. The reason is in `documents/loop-state.json`. Fix that, then let the agent run `bin/autoresearch submit` again. A saved snapshot with an empty decision and no finished panel is reviewed on that retry. Confirmation reviews that already returned are kept. A finished version is not reviewed again.

Spend is `bin/autoresearch usage` in another shell. `--no-live` skips the network lookup.

```
paste loop/prompts/interactive.md
        |
        v
agent works in the open terminal
        |  documents/paper.md
        |  campaign/<id>/
        v
agent runs bin/autoresearch submit
        |  one reviewer
        |  on accept, two more reviewers
        |  all three accept -> documents/REMARK.md
        |  otherwise -> documents/REVIEW.md
        |  git commit and git push
        v
agent runs sleep 600
        |
        +-- REMARK.md or stalled --> agent stops
        +-- REVIEW.md --> next version in the same session
```

`submit` sends `documents/paper.md` and, when that file is new, `documents/response.md`. An unchanged response is withheld. Both texts are copied to `documents/versions/vNNN/` with `manifest.json`. The manifest sets `experimental_data_attached` to false. Code, logs, datasets, and campaign records stay out of the request. The review instruction is `loop/prompts/review.md`.

One reviewer reads that packet first. A rejection ends the round and is stored as `revise`. An acceptance does not finish the campaign. `submit` then makes two more calls with the same instruction and the same packet. Each of those calls is labeled as an independent review and does not include the other reviews. The campaign is accepted only when both accept. `submit` writes all three remarks to `documents/REMARK.md`. If either confirmation reviewer rejects, `submit` writes all three reviews to `documents/REVIEW.md` and the agent continues. The next version starts with one reviewer again. Two further reviewers are called only after that reviewer accepts.

Once three revise decisions exist, the same `submit` also calls `loop/prompts/progress.md` on those three manuscripts. A split panel counts as one revise. The pull is `git pull --rebase --autostash` when the branch has an upstream. With no upstream, `submit` still commits and pushes. Leave `git push`, `git pull`, and `git reset` to `submit`.

On Bouchet, do this inside the agent-partition session you already use for Pi. Load `local-coding-agents` the same way you do for an interactive `pi`. The agent session is one CPU and 8 GB. `submit` runs in that session and does not start another Slurm job.

## Unattended loop

`bin/autoresearch loop` still runs the coding agent as a subprocess, one version at a time, then reviews and pushes. Set the command once. `{prompt_file}` becomes `documents/handoff/prompt.md`, rendered from `loop/prompts/agent_initial.md` or `loop/prompts/agent_continue.md`.

```sh
export AUTORESEARCH_AGENT_COMMAND='your-agent --prompt-file {prompt_file}'
bin/autoresearch loop
```

The subprocess has to write `documents/paper.md` and exit. If it exits without a new manuscript, the loop runs it once more and then blocks. `--max-cycles N` pauses after N cycles. The status stays `running`. The interactive session does not use this command.

## When submit stops

The review scores quality, clarity, significance, and originality from 4 (excellent) to 1 (poor), and gives an overall recommendation from 6 (Strong Accept) to 1 (Strong Reject). The prompt accepts only recommendation 5 or 6. Every other recommendation is stored as `revise`, so a rejected paper continues until the progress check stops it. A useful negative result or a narrowed claim can be accepted when the manuscript stands on its own. Finishing still requires the two confirmation reviewers to accept as well.

Significant progress is a material change in the claim, the evidence, the scope, or the validity of the argument. A narrowing, a withdrawn claim, or a negative result counts when it would change what a careful reader believes. Rewording the same result does not. When the manuscripts are too thin to judge, the progress prompt tells the model to report progress and name the gap.

| Status | Exit | Meaning |
| --- | --- | --- |
| `accepted` | 0 | Three reviewers accepted. |
| `running` | 0 | The review asked for another version. In the unattended loop, `--max-cycles` also leaves the status `running`. |
| `stalled` | 3 | The progress check reported no significant progress. |
| `blocked` | 2 | The brief changed, git failed, `submit` found no manuscript, the provider rejected the call, the reply was unusable, or another `submit` or `loop` holds the lock. |

`--max-cycles N` applies to `bin/autoresearch loop` only. A second `submit` or `loop` in the same checkout blocks on `documents/.loop.lock`.

Accepted and stalled runs stay stopped until `documents/loop-state.json` and `documents/versions/` are removed together. `submit` refuses to overwrite an existing version directory.

A blocked `submit` or `loop` clears that flag on the next run and retries. If a snapshot was saved and the decision is empty, the retry reviews that snapshot. If the first reviewer already accepted and a confirmation call did not finish, the retry calls only the missing reviewers. If the version record already says accept or stall, the retry pushes that result.

The first `submit` pins the SHA-256 of `RESEARCH_BRIEF.md`. A later edit blocks the next `submit`. Keep that state, and start a new run if the brief should change.

Provider HTTP 400, 401, 403, and 404 block immediately. Other provider errors, and a reply that is not the expected JSON, are tried once more and then block. Both the failure and the successful call are appended to the usage ledger.

`bin/autoresearch review` sends the current manuscript once. It writes `documents/reviews/adhoc.md` and updates `documents/REMARK.md` or `documents/REVIEW.md`. It does not convene the two confirmation reviewers, does not move the stop state, and does not create `v000`.

## Files the review leaves behind

Unanimous acceptance writes `documents/REMARK.md`, with all three remarks, and removes `documents/REVIEW.md`. Any other outcome writes `documents/REVIEW.md` and removes `documents/REMARK.md`. A single rejection is that reviewer's text. A split panel is the three reviews under `Reviewer 1`, `Reviewer 2`, and `Reviewer 3`. Each remark names the four scores, the recommendation, and fitting journals or conferences. Each rejection names the supported contribution, the issues that threaten it, required corrections versus optional work, what should stop if the next result fails, and the strongest claim the study can make now.

Each round is also stored as `documents/reviews/vNNN.md` and `documents/reviews/vNNN.json`. The JSON records the round decision and, for a panel, each reviewer's decision. Each progress judgment is stored as `documents/progress/vNNN.json`.

The prompt you paste is `loop/prompts/interactive.md`. The strong-model instructions are `loop/prompts/review.md` and `loop/prompts/progress.md`. The unattended loop uses `loop/prompts/agent_initial.md` and `loop/prompts/agent_continue.md`. Edit those files to change the next call.

## Configuration

Settings resolve in this order: built-in defaults, the provider preset, fields in the config file that belong to the selected provider, then environment variables. `AUTORESEARCH_LOOP_CONFIG` selects a file. Otherwise `submit` reads `loop.config.json` when that file exists. The interactive session needs the reviewer key and, for Azure, the endpoint and deployment name. It does not need an agent command.

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

`git.enabled` defaults to true and `git.remote` defaults to `origin`. Set `git.enabled` to false to run `submit` with no pull or push. `agent.argv`, `agent.prompt_via`, and `agent.timeout_minutes` are for the unattended `bin/autoresearch loop` only. `prompt_via` is `file` (the command must contain `{prompt_file}`), `argv` (the command must contain `{prompt}` or `{prompt_file}`), or `stdin`.

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
| `AUTORESEARCH_AGENT_COMMAND` | Unattended loop only. Research-agent argv. Overrides `agent.argv`. |
| `AUTORESEARCH_PROMPT_VIA` | Unattended loop only. `file`, `argv`, or `stdin`. |
| `AUTORESEARCH_LOOP_CONFIG` | Path to the JSON config. |

## API usage

`bin/autoresearch usage` prints the provider, model, base URL, and a redacted key hint (the variable name and the last four characters). It then sums `usage/api-usage.jsonl`: calls, prompt tokens, completion tokens, and the cost the provider reported. Each line records the time, operation (`review`, `confirmation`, or `progress`), version, status, and request id. `confirmation` is one of the two reviewers called after the first acceptance. The raw key is not written to the ledger, the review, or git.

`--live` is the default. On OpenRouter it queries `GET /api/v1/key` and prints usage, daily, weekly, and monthly figures, the limit and remaining credit, bring-your-own-key usage, and the effective budget when the provider returns them. Providers without a key endpoint print the local ledger and say so. A failed live query is reported and does not fail the command. `--no-live` skips the network.

## Git

With git enabled, each `submit` commits the reviewed version with `git add -A` and pushes with `git push -u <remote> HEAD`. Paths matching `.env`, `.pem`, `.key`, `id_rsa`, `credentials.json`, or a service-account file are unstaged. A staged diff that matches an API-key pattern is unstaged and `submit` blocks. Campaign directories are gitignored, so experiment logs stay local. Manuscripts, reviews, `documents/loop-state.json`, and `usage/api-usage.jsonl` are part of the commit.

`submit` does not rewrite history. A detached `HEAD` blocks the sync. A repository with no `origin` remote is committed locally.

## The research campaign

Inside a version, the agent follows `AGENT_INSTRUCTIONS.md`. It reads the brief, writes `./policy.json` with exactly these keys, and runs `bin/autoresearch init` from the repository root:

`allow_local`, `allow_slurm`, `partitions`, `cpus_max`, `memory_mb_max`, `gpus_max`, `wall_minutes_max`, `concurrency_max`, `attempts_max`, `elapsed_hours_max`, `storage_mb_max`.

`init` checks that those keys are present and well formed. Booleans must be booleans, the numeric caps must be nonnegative, `allow_slurm` requires a non-empty `partitions` list, and at least one of local or Slurm must be authorized. The helper does not enforce the numeric caps at runtime. The agent stays inside the brief.

`init` snapshots the brief into `campaign/<timestamp>-<id>/` and stores its SHA-256. A later edit makes `status` and `report` stop with "brief changed". Keep the old campaign and initialize a new one. `current()` is the lexicographically latest campaign directory that contains `state.json`. `init` reads `./policy.json` from the current working directory, so run it from the repository root. `submit`, `loop`, `usage`, and `review` locate the repository from the `bin/autoresearch` script, independent of the shell's working directory.

Experiments go through `bin/research-job`:

- `local` runs the command when the policy sets `allow_local` and `SLURM_JOB_ID` is set. Without an allocation it refuses.
- `slurm` refuses. The helper accepts a validated policy and does not submit a site job.
- `bin/autoresearch smoke` is the offline mechanics demo. It is the only execution path that runs with no allocation.

`bin/autoresearch stop` creates `campaign/<id>/STOP` and does not cancel running jobs. `start` prints a reminder that the foreground agent runs the campaign. In the interactive session that agent stays open and calls `bin/autoresearch submit` when the manuscript is ready.

## Commands

| Command | Effect |
| --- | --- |
| `bin/autoresearch check` | Print the Python version and whether `sbatch` and `squeue` are on `PATH`. |
| `bin/autoresearch init` | Validate the brief and `./policy.json`, then create `campaign/<id>/`. |
| `bin/autoresearch start` | Print the interactive-session reminder: paste `loop/prompts/interactive.md` and call `submit`. |
| `bin/autoresearch status` | Print the current campaign's state and policy as JSON. Checks the brief hash. |
| `bin/autoresearch report` | Write `report.md` for the current campaign. |
| `bin/autoresearch stop` | Request a graceful stop. Drops `STOP`. Does not cancel jobs. |
| `bin/autoresearch smoke` | Run `examples/smoke_test/`. |
| `bin/autoresearch submit` | Usual path. Review the manuscript already in `documents/paper.md`, sync git, and print the file the agent should read after `sleep 600`. |
| `bin/autoresearch loop` | Unattended alternative. Start the agent, review each version, sync git, and stop on accept or a stalled window. |
| `bin/autoresearch loop --max-cycles N` | Unattended alternative. Stop this process after N cycles. Status stays `running`. |
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
- `loop/`: the `submit` client, provider calls, prompts, and the usage ledger.
- `loop/prompts/interactive.md`: the prompt to paste. This is the usual session.
- `loop/prompts/`: review and progress prompts. `agent_initial.md` and `agent_continue.md` are for the unattended loop.
- `loop.config.example.json`: sample reviewer, git remote, and stop window. The `agent` block is for the unattended loop.
- `documents/paper.md`, `documents/response.md`: the texts the strong model can see.
- `documents/versions/vNNN/`: snapshotted manuscript, optional response, and manifest.
- `documents/reviews/`: `vNNN.md`, `vNNN.json`, and `adhoc.md` from a one-shot review.
- `documents/REMARK.md` or `documents/REVIEW.md`: the latest unanimous accept, or the latest single review or combined panel.
- `documents/progress/`: progress judgments.
- `documents/loop-state.json`: status, brief hash, and per-version decisions.
- `documents/handoff/prompt.md`: the prompt the unattended loop gives the agent. The interactive session does not use it.
- `usage/api-usage.jsonl`: created on the first strong-model call. Key hints only.
- `campaign/<id>/`: brief snapshot, policy, state, ledger, findings, protocol, and one directory per experiment. Gitignored.
- `examples/smoke_test/`: offline demo. Output is gitignored.
- `slurm/agent-session.example.sh`: illustrative session notes.

## Example: Yale Bouchet

The interactive session above is the way to run on Bouchet. Obtain an agent-partition session under the current [YCRC Bouchet documentation](https://docs.ycrc.yale.edu/clusters/bouchet/). Each agent-partition job is limited to one CPU and 8 GB. Check the documentation for current limits. Inside the session, load `local-coding-agents` as documented, load `.env`, and start `pi` in this repository. Paste `loop/prompts/interactive.md`. `python3` on the node has to import this package. Separate Slurm submissions stay refused until a later helper can accept a site-valid job request, and until the brief authorizes them. `status`, `stop`, and `report` still inspect the campaign from that session.

## Testing

`python3 -m pytest tests/` runs offline and uses the stdlib plus pytest.

- `tests/test_smoke.py`: the offline demo exits 0.
- `tests/test_lifecycle.py`: drives a campaign against an isolated copy of the template. Incomplete briefs and invalid policies are rejected. `init`, `status`, `report`, and `stop` behave. Editing the brief after `init` is blocked. The `research-job` guards fire: local unauthorized, no allocation, and Slurm refused. Real local execution runs only when the tests themselves are inside a Slurm allocation.
- `tests/test_loop.py`: a fake agent and a fake HTTP transport cover the OpenRouter and GPT-6 Sol defaults, manuscript-only requests, the three-reviewer accept panel, stall, usage redaction, the provider wires (including Azure), and git refusal of `.env` and key material.

## Resource and safety rules

For work inside the current allocation, confirm that the job fits that allocation. Further Slurm jobs, extra GPUs, other partitions, network, paid services, external paths, or extra concurrency require an explicit statement in the brief. Confirm partition, account, QoS, reservation, and the CPU, GPU, memory, time, concurrency, and budget figures before any submission. If a required scheduler value is missing, record a blocker and stop. Do not run experiments on login nodes. `slurm/agent-session.example.sh` is an illustration. Check the site before using it. If Slurm is unavailable, real execution stops. Smoke stays available offline.

At `init`, keep the brief snapshot and hash, the policy, the assumptions, the protocol, and the campaign id. Each trial gets its own directory, proposal, manifest, logs, result, and analysis. Record failed and inconclusive outcomes. Compare compatible protocols, and include uncertainty for noisy results. Track requested use against observed use. A stop file prevents new work and does not cancel active jobs. After a brief change, keep the old campaign and create a new one.

## Limitations

The campaign helper does not parse the brief into permissions, and it does not submit Slurm jobs. `bin/autoresearch submit` does call the configured strong model, and the request is the manuscript plus a new author response. A live agent has to write `policy.json` and any site-specific scheduler details before real compute. Until that exists, use `bin/autoresearch smoke` for experiments. Initialize and recovery locking for campaigns, full accounting, numeric budget enforcement, and a durable campaign ledger are not implemented. The template is not evidence that resource caps are enforced. Do not launch a real campaign while you are only setting up the template. Strong-model calls spend the configured API key. `bin/autoresearch usage` is the record of that spend.
