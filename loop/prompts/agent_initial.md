This prompt is only for the unattended command `bin/autoresearch loop`. The usual session is interactive: a person pastes `loop/prompts/interactive.md` and the agent calls `bin/autoresearch submit`.

Read AGENTS.md, AGENT_INSTRUCTIONS.md, and the complete RESEARCH_BRIEF.md. Derive and validate a bounded policy. Initialize a campaign only when the brief is complete and the policy is safe. Run one reviewable version of the research. Record blockers in the campaign record. The brief is the only human input for this campaign.

This process is version {next_version}. Finish this version, then exit so the supervisor can send the manuscript to the strong model.

Done when all of these are true:
- documents/paper.md is the full manuscript for this version and can be judged without any other project file.
- Experimental records, logs, datasets, and campaign files stay in the campaign directory.
- The process exits.

The supervisor calls the strong model, pulls, commits, and pushes. Leave git push, git pull, and git reset to the supervisor.
