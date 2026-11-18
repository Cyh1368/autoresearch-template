"""Strong-model review and git sync for an interactive research session.

The usual entry is ``bin/autoresearch submit``. The person drives the coding
agent and pastes ``loop/prompts/interactive.md``. ``bin/autoresearch loop`` is
the unattended alternative and starts the agent itself.

The campaign helper in ``core.runner`` stays fail-closed. This package does not
read the brief into permissions and does not submit cluster jobs.

Acceptance takes three reviewers. The first rejection ends the round. The first
acceptance is checked by two more reviewers, and both must accept.
"""
