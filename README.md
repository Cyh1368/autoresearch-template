# Autoresearch template

A transparent starter for computational research controlled by one natural-language brief. The live coding agent owns the iterative loop; the CLI provides deterministic checks and state helpers and does not launch a coding agent in the background. The policy file is agent-derived and must be reviewed against the brief; language interpretation is not a security boundary.

## Quick start

1. Copy this directory to the campaign project and edit only `RESEARCH_BRIEF.md`.
2. Obtain a Bouchet agent-partition session under current [YCRC Bouchet documentation](https://docs.ycrc.yale.edu/clusters/bouchet/). Each agent-partition job is limited to one CPU and 8 GB; check documentation for current limits. Within the session, consult local instructions and load `local-coding-agents` as documented.
3. Start your supported coding agent in this directory and give it: `Read AGENTS.md, AGENT_INSTRUCTIONS.md, and the complete RESEARCH_BRIEF.md. Derive and validate a bounded policy, initialize only if safe, then execute the documented research loop autonomously. Do not start a real campaign unless the brief is complete and authorizes it.`
4. Use `bin/autoresearch status`, `bin/autoresearch stop`, and `bin/autoresearch report` to inspect/control.

The controller is the foreground coding-agent process. If its interface exits, the loop pauses. A submitted experiment job can outlive it; resume by reconciling scheduler state before any new run. No automatic controller resubmission occurs.

## Commands and layout

`bin/autoresearch check|init|start|status|stop|report|smoke`. `init` intentionally refuses to invent policy; the agent must derive it. `bin/research-job` is fail-closed outside the explicitly tiny smoke mode. Campaign outputs belong under `campaign/<id>`; never overwrite an existing campaign. The smoke example writes to `examples/smoke_test/output` and is a mechanics demonstration, not research.

For computational work inside the existing allocation, verify resources fit the allocation. Additional Slurm jobs, GPU, other partitions, network, paid services, external paths, or extra concurrency require explicit brief authorization. Validate partition/account/QoS/reservation and CPU/GPU/memory/time/concurrency/budget before submission. If required scheduler details are absent, stop with a blocker. Do not experiment on login nodes. The Slurm session script is illustrative only; site settings must be checked. Slurm unavailable means real execution stops; smoke remains offline.

The full loop and artifact expectations are in `AGENT_INSTRUCTIONS.md`. At campaign initialization preserve a brief snapshot/hash, policy provenance, assumptions, protocol, lifecycle state and unique ID. Each trial gets an isolated directory, proposal, manifest, logs, result and analysis. Record failed and inconclusive outcomes. Compare only compatible protocols; include uncertainty for noisy results. Track requested versus observed usage. A safe stop prevents new work and does not cancel active jobs by default. Keep the old campaign when changing the brief; create a new campaign explicitly.

## Limitations

This starter deliberately does not parse natural language into permissions or submit Slurm jobs automatically: its current deterministic helper rejects those operations rather than risk accidental access. A live agent must implement/validate explicit policy and cluster-specific scheduler details before real work; until that exists, use only the offline smoke. Initialize/recovery locking, full accounting, budget enforcement, and durable campaign ledger are not yet implemented. Never treat this template as proof that resource limits are enforced. Do not launch a real campaign during template setup.
