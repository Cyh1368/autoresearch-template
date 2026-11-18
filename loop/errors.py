"""Errors the supervisor reports without a traceback."""


class LoopBlock(ValueError):
    """Stop the loop until a person fixes the recorded condition."""


class ProviderError(ValueError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class GitError(ValueError):
    """Git sync could not finish."""
