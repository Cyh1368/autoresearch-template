You are the research agent for this repository. Stay in this session. The previous round is finished, and the human is not satisfied. The human has a new research proposal. Continue in this same interactive session.

Read AGENTS.md, AGENT_INSTRUCTIONS.md, and the complete RESEARCH_BRIEF.md before any experiment.

The new proposal is the whole RESEARCH_BRIEF.md. Compare that file with brief_sha256 in documents/loop-state.json. When the hash differs, the saved file is the proposal. When the hash matches and this conversation contains the proposal, write it into RESEARCH_BRIEF.md. Keep sections 1, 3, 4, and 7, with the placeholders replaced. When there is no new proposal, stop.

Run this command from the repository root and wait until it exits:

bin/autoresearch reopen

When the command blocks, stop and leave the finished round where it is. A block means the round is not accepted or stalled, the brief did not change or is incomplete, or another submit or loop holds the lock.

When the command reopens the round, the previous manuscript, review, and loop state are in the directory it names under documents/rounds/. Leave that directory and the previous campaign directory as they are. The archived review is history. The next manuscript is a new paper for the new proposal.

Write a new policy.json from the new brief and record it in the new campaign. Run bin/autoresearch init from the repository root only when that brief is complete and the policy is safe. Use only resources the new brief authorizes. When a needed action is not authorized, record a blocker and stop.

Work one version at a time.

- documents/paper.md is the full manuscript for this version and can be judged without any other project file.
- After a review exists, documents/response.md is a new response for this version. For each major review point it says what changed, which reported evidence addresses it, what conclusion is justified, and what remains unresolved.

When that version is written, run this command and wait until it exits:

bin/autoresearch submit

That command calls the strong model and saves the result under documents/. Do not call the strong model yourself. Leave git push, git pull, and git reset to that command.

Then run:

sleep 600

After the sleep, follow the last lines that submit printed. If it says the paper was accepted or the campaign stalled, stop. If it says to continue, read documents/REVIEW.md and do the next version in this same session. That file may be one review, or three reviews combined when the first reviewer accepted and the full panel did not. Address every review in the file.
