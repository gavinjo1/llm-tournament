"""Check that a model answers, how fast, and whether it returns usable JSON.

    python scripts/check_model.py deepseek/deepseek-chat
    python scripts/check_model.py openai/gpt-6-luna none   # with reasoning off

Makes 2 small calls (well under a cent). Reads the API key from the
environment, like the tournament does.
"""

import asyncio
import sys
import time
from pathlib import Path

import litellm
from dotenv import load_dotenv


async def call(model: str, prompt: str, max_tokens: int, reasoning_effort: str | None) -> None:
    start = time.time()
    extra = {} if reasoning_effort is None else {"reasoning_effort": reasoning_effort}
    try:
        response = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            timeout=60,
            num_retries=0,
            **extra,
        )
    except Exception as exc:
        print(f"  FAILED after {time.time() - start:.1f}s: {type(exc).__name__}: {str(exc)[:300]}")
        return
    usage = response.usage
    print(f"  OK in {time.time() - start:.1f}s, {usage.prompt_tokens} in / {usage.completion_tokens} out")
    print(f"  model: {response.model}")
    print(f"  reply: {response.choices[0].message.content!r}")


async def main(model: str, reasoning_effort: str | None) -> None:
    print("1. Tiny call")
    await call(model, "Say hi in one word.", 10, reasoning_effort)
    print("2. JSON call")
    await call(
        model,
        'Reply with only this JSON object and nothing else: {"public_message": "hello"}',
        50,
        reasoning_effort,
    )


if __name__ == "__main__":
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")  # API keys from .env
    model = sys.argv[1] if len(sys.argv) > 1 else "deepseek/deepseek-chat"
    effort = sys.argv[2] if len(sys.argv) > 2 else None
    asyncio.run(main(model, effort))
