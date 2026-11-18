Read AGENT_INSTRUCTIONS.md and the complete RESEARCH_BRIEF.md before acting. Follow the campaign lifecycle exactly; never infer permission for resources or actions.

The usual session is interactive. A person pastes `loop/prompts/interactive.md` and stays in this terminal. Write `documents/paper.md`, then run `bin/autoresearch submit`, sleep 600 seconds, and continue from the review it saved. `bin/autoresearch loop` is the unattended alternative.

After an accepted or stalled round, when the human replaces `RESEARCH_BRIEF.md` and pastes `loop/prompts/interactive_reopen.md`, run `bin/autoresearch reopen`, then continue in this terminal with `bin/autoresearch submit` and sleep 600.
