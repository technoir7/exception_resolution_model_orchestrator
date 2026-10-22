"""
Which way Claude is called: the `claude` command on your own login (no key,
a subscription pays), or the API with a key (for a server, or Docker).
"""

from apps.api.config import settings
from apps.api.services.anthropic_provider import ClaudeAPI
from apps.api.services.claude_provider import ClaudeCLI
from apps.api.services.llm_provider import LLMProvider, ModelUnavailable


def model(name: str) -> LLMProvider:
    """A provider for `name` ('haiku', 'sonnet' or 'opus')."""
    if settings.claude_via == "cli":
        return ClaudeCLI(name)
    if settings.claude_via == "api":
        if not settings.anthropic_api_key:
            raise ModelUnavailable("CLAUDE_VIA is 'api' but ANTHROPIC_API_KEY is not set")
        return ClaudeAPI(name, settings.anthropic_api_key)
    raise ValueError(f"CLAUDE_VIA must be 'cli' or 'api', not {settings.claude_via!r}")
