"""
Claude as the reviewing model, through the `claude` command and your own login.

Calling the CLI rather than the API lets a Claude subscription pay for the
reviews, with no API key to manage. Each call is stripped back to a plain
completion: no tools, no MCP servers, no settings from the directory it runs
in, and no saved session. The CLI reports what each call would cost at API list
prices, which is what the cost figures use.
"""

import asyncio
import json
import time
from decimal import Decimal
from typing import Awaitable, Callable, List, Optional, Tuple, Type

from pydantic import BaseModel

from apps.api.models.cost import ModelTier
from apps.api.services.llm_provider import LLMProvider, LLMResponse

# The CLI's aliases follow the newest model of each size.
TIER_MODELS = {ModelTier.TIER_A: "haiku", ModelTier.TIER_B: "sonnet", ModelTier.TIER_C: "opus"}

SYSTEM_PROMPT = "Reply to the message."
TIMEOUT_SECONDS = 180

Run = Callable[[List[str], str], Awaitable[Tuple[int, str, str]]]


class ClaudeCLIError(Exception):
    pass


async def _run(args: List[str], prompt: str) -> Tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(prompt.encode()), TIMEOUT_SECONDS)
    return process.returncode, stdout.decode(), stderr.decode()


class ClaudeCLI(LLMProvider):
    def __init__(self, model: str, run: Run = _run):
        self.model = model
        self.run = run

    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> LLMResponse:
        args = [
            "claude", "-p",
            "--model", self.model,
            "--output-format", "json",
            "--tools", "",
            "--safe-mode",
            "--strict-mcp-config",
            "--no-session-persistence",
            "--system-prompt", system_prompt or SYSTEM_PROMPT,
        ]
        started = time.monotonic()
        try:
            code, stdout, stderr = await self.run(args, prompt)
        except FileNotFoundError as error:
            raise ClaudeCLIError("the claude command is not installed here (set REVIEW_WITH_MODELS=false "
                                 "to process invoices without models)") from error
        except asyncio.TimeoutError as error:
            raise ClaudeCLIError(f"no reply within {TIMEOUT_SECONDS} seconds") from error
        if code != 0:
            raise ClaudeCLIError((stderr or stdout).strip())
        reply = json.loads(stdout)
        if reply.get("is_error"):
            raise ClaudeCLIError(reply.get("result", "unknown error"))
        usage = reply.get("usage", {})
        input_tokens = sum(usage.get(k, 0) for k in
                           ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        output_tokens = usage.get("output_tokens", 0)
        return LLMResponse(
            content=reply["result"],
            model_id=next(iter(reply.get("modelUsage", {})), self.model),
            model_tier=self.get_tier(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            latency_ms=int((time.monotonic() - started) * 1000),
            raw_response=reply,
            cost_usd=Decimal(str(reply.get("total_cost_usd", 0))),
        )

    def get_model_id(self) -> str:
        return self.model

    def get_tier(self) -> ModelTier:
        return next(tier for tier, model in TIER_MODELS.items() if model == self.model)

    def get_cost_per_1k_tokens(self) -> Decimal:
        raise NotImplementedError("the CLI reports each call's cost; there is no fixed rate")
