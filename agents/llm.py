"""An LLM player. Calls any provider through LiteLLM.

Model ids follow LiteLLM, e.g. "anthropic/claude-haiku-5-5",
"deepseek/deepseek-chat", "gemini/...", "openrouter/...". API keys come from
the usual environment variables (ANTHROPIC_API_KEY, OPENAI_API_KEY, ...).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from agents.prompts import build_messages
from agents.ratelimit import RateLimiter
from engine.agent import Agent, AgentFailure, Observation


@dataclass
class Completion:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0


CompletionFn = Callable[..., Awaitable[Completion]]


async def litellm_completion(
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    reasoning_effort: str | None = None,
) -> Completion:
    import litellm  # slow to import; only needed for real runs

    litellm.suppress_debug_info = True  # errors are recorded in the trace instead
    extra = {} if reasoning_effort is None else {"reasoning_effort": reasoning_effort}
    response = await litellm.acompletion(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        num_retries=3,
        timeout=120,
        **extra,
    )
    try:
        cost = float(litellm.completion_cost(completion_response=response))
    except Exception:  # unknown price for this model
        cost = 0.0
    usage = response.usage
    return Completion(
        text=response.choices[0].message.content or "",
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        cost=cost,
    )


class LLMAgent(Agent):
    def __init__(
        self,
        model: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 800,
        persona: str | None = None,
        reasoning_effort: str | None = None,
        completion: CompletionFn = litellm_completion,
        limiter: RateLimiter | None = None,
    ) -> None:
        """reasoning_effort: "none" turns a thinking model's reasoning off; None
        leaves the provider's default. limiter: shared by every seat using the
        same API quota."""
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.persona = persona
        self.reasoning_effort = reasoning_effort
        self._complete = completion
        self._limiter = limiter
        self.notes: list[str] = []
        self.trace: list[dict[str, Any]] = []
        self.usage = {"calls": 0, "errors": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0}

    @property
    def label(self) -> str:
        return self.model

    def settings(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "reasoning_effort": self.reasoning_effort,
        }

    def usage_report(self) -> dict[str, Any]:
        return {**self.usage, "settings": self.settings()}

    async def act(self, obs: Observation) -> dict[str, Any] | str:
        messages = build_messages(obs, self.notes, self.persona)
        started = time.time()
        entry: dict[str, Any] = {
            "time": started,
            "player": obs.you,
            "model": self.model,
            "day": obs.day,
            "round": obs.round,
            "kind": obs.kind,
            "settings": self.settings(),
            "messages": messages,
        }
        if self._limiter is not None:
            await self._limiter.acquire()
        started = time.time()  # latency excludes time spent waiting for the limiter
        self.usage["calls"] += 1
        try:
            extra = {} if self.reasoning_effort is None else {"reasoning_effort": self.reasoning_effort}
            reply = await self._complete(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                **extra,
            )
        except Exception as exc:  # API failure after LiteLLM's own retries
            self.usage["errors"] += 1
            error = f"{type(exc).__name__}: {exc}"
            entry.update(error=error, seconds=time.time() - started)
            self.trace.append(entry)
            raise AgentFailure(f"{self.model}: {error}") from exc

        self.usage["prompt_tokens"] += reply.prompt_tokens
        self.usage["completion_tokens"] += reply.completion_tokens
        self.usage["cost"] += reply.cost
        entry.update(
            response=reply.text,
            prompt_tokens=reply.prompt_tokens,
            completion_tokens=reply.completion_tokens,
            cost=reply.cost,
            seconds=time.time() - started,
        )
        self.trace.append(entry)

        parsed = extract_json(reply.text)
        if isinstance(parsed, dict) and isinstance(parsed.get("private_reasoning"), str):
            reasoning = parsed["private_reasoning"].strip()
            if reasoning:
                where = f"Day {obs.day}" + (f" R{obs.round}" if obs.round is not None else "")
                self.notes.append(f"{where} ({obs.kind}): {reasoning}")
        return parsed


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> dict[str, Any] | str:
    """The first JSON object in a reply, tolerating code fences and chatter.

    Returns the raw text if there is none, so the engine reports the error.
    """
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    decoder = json.JSONDecoder()
    for candidate in candidates:
        for start in (i for i, ch in enumerate(candidate) if ch == "{"):
            try:
                value, _ = decoder.raw_decode(candidate, start)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
    return text
