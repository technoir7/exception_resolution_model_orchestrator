"""Calling Claude through the API with a key, for a server with no `claude`
command, and pricing each call from its tokens."""

import base64
import json
from decimal import Decimal

import httpx
import pytest

from apps.api.services import claude
from apps.api.services.anthropic_provider import ClaudeAPI, price
from apps.api.services.claude_provider import ClaudeCLI
from apps.api.services.llm_provider import ModelUnavailable

KEY = "sk-ant-test-not-a-real-key"


def answer(text='{"decision": "pay"}', model="claude-haiku-5-5", input_tokens=2858, output_tokens=700):
    return {"type": "message", "model": model, "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn", "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens}}


class Api:
    """Answers each request with the next of `replies`: (status, body)."""

    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status, body = self.replies.pop(0)
        return httpx.Response(status, json=body)

    def sent(self, i=-1):
        return json.loads(self.requests[i].content)


async def no_wait(seconds):
    pass


def provider(api, model="haiku"):
    return ClaudeAPI(model, KEY, transport=httpx.MockTransport(api), sleep=no_wait)


class TestAskingForAVerdict:
    async def test_sends_the_prompt_to_the_model_with_the_key(self):
        api = Api((200, answer()))
        await provider(api).complete("Decide this invoice.")
        request = api.requests[0]
        assert request.url == "https://api.anthropic.com/v1/messages"
        assert request.headers["x-api-key"] == KEY and request.headers["anthropic-version"]
        assert api.sent()["model"] == "claude-haiku-5-5"
        assert api.sent()["messages"] == [{"role": "user", "content": "Decide this invoice."}]

    async def test_asks_as_the_benchmark_did(self):
        """The CLI set no temperature, so neither does the API."""
        api = Api((200, answer()))
        await provider(api).complete("x")
        assert "temperature" not in api.sent()

    async def test_returns_the_reply_its_tokens_and_what_it_cost(self):
        response = await provider(Api((200, answer()))).complete("x")
        assert response.content == '{"decision": "pay"}'
        assert (response.model_id, response.input_tokens, response.output_tokens) == ("claude-haiku-5-5", 2858, 700)
        assert response.cost_usd == Decimal("0.0006358")


class TestReadingAPdf:
    async def test_sends_the_file_whole_with_the_instruction(self):
        api = Api((200, answer("{}")))
        await provider(api).read(b"%PDF-1.4 x", "Copy this invoice.")
        [document, instruction] = api.sent()["messages"][0]["content"]
        assert document["type"] == "document"
        assert document["source"] == {"type": "base64", "media_type": "application/pdf",
                                      "data": base64.b64encode(b"%PDF-1.4 x").decode()}
        assert instruction == {"type": "text", "text": "Copy this invoice."}


class TestPrices:
    def test_are_anthropics_list_prices_per_million_tokens(self):
        assert price("claude-haiku-5-5", 100_000, 0) == Decimal("0.01")
        assert price("claude-sonnet-5-5", 1_000_000, 1_000_000) == Decimal("12")
        assert price("claude-opus-5-5", 0, 1_000_000) == Decimal("20")

    def test_haiku_costs_more_for_a_prompt_over_100000_tokens(self):
        assert price("claude-haiku-5-5", 100_001, 0) == Decimal("0.0500005")

    def test_an_unpriced_model_is_an_error_not_free(self):
        with pytest.raises(ValueError, match="no price"):
            price("claude-unknown", 10, 10)


class TestWhenTheApiFails:
    async def test_an_overloaded_api_is_asked_again(self):
        api = Api((529, {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}),
                  (200, answer()))
        assert (await provider(api).complete("x")).content == '{"decision": "pay"}'
        assert len(api.requests) == 2

    async def test_says_why_and_never_shows_the_key(self):
        api = Api((400, {"type": "error", "error": {"type": "invalid_request_error", "message": "prompt is too long"}}))
        with pytest.raises(ModelUnavailable, match="prompt is too long") as error:
            await provider(api).complete("x")
        assert KEY not in str(error.value)

    async def test_gives_up_after_a_few_tries(self):
        busy = (529, {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}})
        api = Api(busy, busy, busy)
        with pytest.raises(ModelUnavailable, match="Overloaded"):
            await provider(api).complete("x")
        assert len(api.requests) == 3

    async def test_an_unreachable_api_is_unavailable(self):
        def down(request):
            raise httpx.ConnectError("no route to host")
        with pytest.raises(ModelUnavailable):
            await ClaudeAPI("haiku", KEY, transport=httpx.MockTransport(down), sleep=no_wait).complete("x")


class TestChoosingHowToCallClaude:
    def test_the_cli_by_default(self):
        assert isinstance(claude.model("haiku"), ClaudeCLI)

    def test_the_api_with_a_key(self, monkeypatch):
        from apps.api.config import settings
        monkeypatch.setattr(settings, "claude_via", "api")
        monkeypatch.setattr(settings, "anthropic_api_key", KEY)
        assert isinstance(claude.model("haiku"), ClaudeAPI)

    def test_the_api_without_a_key_is_an_error_at_once(self, monkeypatch):
        from apps.api.config import settings
        monkeypatch.setattr(settings, "claude_via", "api")
        monkeypatch.setattr(settings, "anthropic_api_key", None)
        with pytest.raises(ModelUnavailable, match="ANTHROPIC_API_KEY"):
            claude.model("haiku")

    def test_the_cli_fails_the_same_way_as_the_api(self):
        from apps.api.services.claude_provider import ClaudeCLIError
        assert issubclass(ClaudeCLIError, ModelUnavailable)
