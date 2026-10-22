"""Calling Claude through the `claude` command, and what each call cost."""

import json
from decimal import Decimal

import pytest

from apps.api.models.cost import ModelTier
from apps.api.services.claude_provider import ClaudeCLI, ClaudeCLIError, TIER_MODELS


def reply(result="{}", cost=0.0123, is_error=False):
    return json.dumps({
        "result": result, "is_error": is_error, "total_cost_usd": cost,
        "usage": {"input_tokens": 10, "cache_creation_input_tokens": 500, "cache_read_input_tokens": 0,
                  "output_tokens": 40},
        "modelUsage": {"claude-haiku-5-5": {"costUSD": cost}},
    })


class FakeRun:
    def __init__(self, stdout, returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr
        self.calls = []

    async def __call__(self, args, prompt):
        self.calls.append((args, prompt))
        return self.returncode, self.stdout, self.stderr


async def test_returns_the_reply_and_what_it_cost():
    run = FakeRun(reply('{"decision": "pay"}', cost=0.0123))
    response = await ClaudeCLI("haiku", run=run).complete("Decide this invoice.")
    assert response.content == '{"decision": "pay"}'
    assert response.cost_usd == Decimal("0.0123")
    assert response.model_id == "claude-haiku-5-5"
    assert response.input_tokens == 510
    assert response.output_tokens == 40


async def test_sends_the_prompt_as_a_plain_completion():
    run = FakeRun(reply())
    await ClaudeCLI("opus", run=run).complete("Decide this invoice.")
    [(args, prompt)] = run.calls
    assert prompt == "Decide this invoice."
    assert args[args.index("--model") + 1] == "opus"
    assert args[args.index("--tools") + 1] == ""
    assert "--no-session-persistence" in args


@pytest.mark.parametrize("run", [FakeRun("", returncode=1, stderr="not logged in"),
                                 FakeRun(reply("rate limited", is_error=True))])
async def test_raises_rather_than_return_an_error_as_text(run):
    with pytest.raises(ClaudeCLIError):
        await ClaudeCLI("haiku", run=run).complete("x")


def test_the_three_tiers_are_three_sizes_of_claude():
    assert TIER_MODELS == {ModelTier.TIER_A: "haiku", ModelTier.TIER_B: "sonnet", ModelTier.TIER_C: "opus"}


async def test_a_missing_claude_command_is_a_failed_call():
    """In Docker, say, where it is not installed: the invoice then goes to a
    person, rather than the pipeline crashing."""
    async def missing(args, prompt):
        raise FileNotFoundError("claude")
    with pytest.raises(ClaudeCLIError, match="not installed"):
        await ClaudeCLI("haiku", run=missing).complete("x")
