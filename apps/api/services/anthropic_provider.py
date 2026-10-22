"""
Claude through the API, with a key: for a server, or Docker, where there is
no `claude` command logged in.

The API reports tokens, not cost, so each call is priced from Anthropic's
list prices. The request is the one the CLI made in the benchmark: the same
system prompt, no temperature, no tools.
"""

import asyncio
import base64
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Awaitable, Callable, List, Optional, Type

import httpx
from pydantic import BaseModel

from apps.api.services.claude_provider import SYSTEM_PROMPT, TIER_MODELS
from apps.api.services.llm_provider import LLMProvider, LLMResponse, ModelUnavailable

URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
# Enough for a verdict, or for every line of a long invoice copied out.
MAX_TOKENS = 4096
TIMEOUT_SECONDS = 180
# Overloaded, rate-limited or failing for a moment: worth asking again.
RETRY_STATUSES = {429, 500, 502, 503, 504, 529}
ATTEMPTS = 3

MODEL_IDS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}


@dataclass(frozen=True)
class Price:
    """USD per million tokens."""
    input: Decimal
    output: Decimal
    # Haiku 5.5 charges more for every token of a prompt over this many.
    long_prompt: Optional[int] = None
    long_input: Optional[Decimal] = None
    long_output: Optional[Decimal] = None


# platform.claude.com/docs/en/about-claude/pricing, October 2026. No prompt
# caching or batching is used, so only the base rates apply.
PRICES = {
    "claude-haiku-5-5": Price(Decimal("0.10"), Decimal("0.50"), 100_000, Decimal("0.50"), Decimal("2.50")),
    "claude-sonnet-5-5": Price(Decimal("2"), Decimal("10")),
    "claude-opus-5-5": Price(Decimal("4"), Decimal("20")),
}


def price(model_id: str, input_tokens: int, output_tokens: int) -> Decimal:
    if model_id not in PRICES:
        raise ValueError(f"no price on file for {model_id}; add it to PRICES")
    p = PRICES[model_id]
    long = p.long_prompt is not None and input_tokens > p.long_prompt
    per_input, per_output = (p.long_input, p.long_output) if long else (p.input, p.output)
    return (input_tokens * per_input + output_tokens * per_output) / 1_000_000


class ClaudeAPI(LLMProvider):
    def __init__(self, model: str, api_key: str, transport: Optional[httpx.AsyncBaseTransport] = None,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self.model = model
        self.model_id = MODEL_IDS.get(model, model)
        self.api_key = api_key
        self.transport = transport
        self.sleep = sleep

    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = MAX_TOKENS,
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> LLMResponse:
        return await self._call(prompt, system_prompt)

    async def read(self, document: bytes, instruction: str) -> LLMResponse:
        """The model's reply to an instruction about a PDF, given whole."""
        return await self._call([
            {"type": "document",
             "source": {"type": "base64", "media_type": "application/pdf",
                        "data": base64.b64encode(document).decode()}},
            {"type": "text", "text": instruction},
        ])

    async def _call(self, content, system_prompt: Optional[str] = None) -> LLMResponse:
        body = {"model": self.model_id, "max_tokens": MAX_TOKENS, "system": system_prompt or SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": content}]}
        headers = {"x-api-key": self.api_key, "anthropic-version": API_VERSION}
        started = time.monotonic()
        async with httpx.AsyncClient(transport=self.transport, timeout=TIMEOUT_SECONDS) as client:
            for attempt in range(ATTEMPTS):
                try:
                    response = await client.post(URL, json=body, headers=headers)
                except httpx.HTTPError as error:
                    problem = f"the Claude API could not be reached: {type(error).__name__}"
                else:
                    if response.status_code == 200:
                        return self._response(response.json(), started)
                    problem = f"the Claude API answered {response.status_code}: {_message(response)}"
                    if response.status_code not in RETRY_STATUSES:
                        break
                if attempt < ATTEMPTS - 1:
                    await self.sleep(2 ** attempt)
        raise ModelUnavailable(problem)

    def _response(self, reply: dict, started: float) -> LLMResponse:
        usage = reply["usage"]
        input_tokens, output_tokens = usage["input_tokens"], usage["output_tokens"]
        text = "".join(block["text"] for block in reply["content"] if block["type"] == "text")
        return LLMResponse(
            content=text,
            model_id=reply["model"],
            model_tier=self.get_tier(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            latency_ms=int((time.monotonic() - started) * 1000),
            raw_response=reply,
            cost_usd=price(self.model_id, input_tokens, output_tokens),
        )

    def get_model_id(self) -> str:
        return self.model_id

    def get_tier(self):
        return next(tier for tier, model in TIER_MODELS.items() if model == self.model)

    def get_cost_per_1k_tokens(self) -> Decimal:
        raise NotImplementedError("input and output tokens are priced differently; see price()")


def _message(response: httpx.Response) -> str:
    try:
        return response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return response.text[:300]
