"""
Async LLM client — supports OAI-compatible endpoints and native Anthropic SDK.

Each agent gets its own API call — never share context between agents.

Routing logic:
  - If ``base_url`` has hostname ``api.anthropic.com`` the call is forwarded to
    the ``anthropic`` SDK (native Anthropic transport, correct auth headers,
    /v1/messages endpoint, extended-thinking support).
  - All other ``base_url`` values use the generic OAI-compatible httpx path
    (``/chat/completions`` with ``Authorization: Bearer``).
"""

import asyncio
import httpx
import json
import logging
import re
from typing import AsyncIterator, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Retryable HTTP status codes
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# ---------------------------------------------------------------------------
# Anthropic URL detection
# ---------------------------------------------------------------------------

_ANTHROPIC_HOST = "api.anthropic.com"

# Models that support extended thinking (claude-3-7+ and claude-*-4+ families only)
# NOTE: claude-3-5-sonnet and claude-3-5-haiku do NOT support extended thinking.
# Only claude-3-7-sonnet and the claude-*-4 generation onwards have this capability.
_ANTHROPIC_THINKING_MODELS = (
    "claude-3-7",
    "claude-opus-4",
    "claude-sonnet-4",
    "claude-haiku-4",
)


def _is_anthropic_url(base_url: str) -> bool:
    """
    Return True when *base_url* hostname is exactly ``api.anthropic.com``.

    Uses ``urllib.parse.urlparse`` to extract the hostname so that URLs such as
    ``https://evil.api.anthropic.com.attacker.com/v1`` are not mistakenly
    treated as Anthropic endpoints.
    """
    if not base_url:
        return False
    try:
        hostname = urlparse(base_url).hostname or ""
        return hostname == _ANTHROPIC_HOST
    except Exception:
        return False


def _anthropic_model_supports_thinking(model: str) -> bool:
    """Return True for Anthropic models that accept a ``thinking`` block."""
    return any(model.startswith(prefix) for prefix in _ANTHROPIC_THINKING_MODELS)


def _anthropic_thinking_budget(max_tokens: int) -> int:
    """
    Compute the extended-thinking budget for an Anthropic request.

    Anthropic recommends leaving ~20 % of tokens for the final response, so
    the thinking budget is capped at 80 % of ``max_tokens``.  The minimum of
    1 024 tokens matches Anthropic's documented minimum budget for meaningful
    chain-of-thought output.
    """
    # 80 % leaves headroom for the visible response after thinking is done.
    # 1 024 is the smallest budget that consistently produces useful reasoning.
    return max(1024, int(max_tokens * 0.8))


async def close_client():
    """No-op — kept for backward compatibility with main.py lifespan hook."""
    pass


# ---------------------------------------------------------------------------
# Native Anthropic SDK helpers
# ---------------------------------------------------------------------------

def _extract_system_from_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """
    Pull out ``system`` role messages from an OAI message list.

    Anthropic's ``/v1/messages`` takes ``system`` as a top-level parameter,
    not inside the ``messages`` array.

    Returns:
        (system_text, filtered_messages)
    """
    system_parts: list[str] = []
    filtered: list[dict] = []
    for msg in messages:
        if msg.get("role") == "system":
            content = msg.get("content", "")
            if isinstance(content, str):
                system_parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        system_parts.append(block.get("text", ""))
        else:
            filtered.append(msg)
    return "\n\n".join(system_parts), filtered


def _anthropic_response_to_oai(message) -> dict:
    """
    Map an ``anthropic.types.Message`` to the OAI ``chat/completions`` response
    shape that the rest of the engine expects.

    The ``content`` field is kept as the original list of typed blocks so that
    ``_extract_thinking_from_response()`` can handle thinking blocks natively.
    """
    content_blocks = []
    for block in message.content:
        block_dict = {"type": block.type}
        if block.type == "thinking":
            block_dict["thinking"] = getattr(block, "thinking", "")
        elif block.type == "text":
            block_dict["text"] = getattr(block, "text", "")
        else:
            # tool_use, redacted_thinking, etc. — best-effort passthrough
            block_dict["text"] = getattr(block, "text", "") or str(block)
        content_blocks.append(block_dict)

    return {
        "id": getattr(message, "id", ""),
        "object": "chat.completion",
        "model": getattr(message, "model", ""),
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": content_blocks,
            },
            "finish_reason": getattr(message, "stop_reason", "end_turn"),
        }],
        "usage": {
            "prompt_tokens": getattr(getattr(message, "usage", None), "input_tokens", 0),
            "completion_tokens": getattr(getattr(message, "usage", None), "output_tokens", 0),
        },
    }


async def _anthropic_chat_completion(
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    json_mode: bool,
    agent_name: str,
) -> dict:
    """
    Native Anthropic SDK path for ``chat_completion()``.

    Handles:
      - System-message extraction
      - Extended thinking for supported models (budget = 80 % of max_tokens,
        temperature forced to 1.0 as Anthropic requires)
      - JSON-mode emulation via a system instruction
      - Retry / fallback on transient errors

    Returns an OAI-shaped dict so callers need no changes.
    """
    try:
        import anthropic as _anthropic  # local import to avoid hard dep at module level
    except ImportError:
        logger.error(
            "The 'anthropic' package is not installed. "
            "Run `pip install anthropic>=0.40.0` to enable native Anthropic support."
        )
        return _fallback_response(agent_name)

    system_text, filtered_messages = _extract_system_from_messages(messages)

    if json_mode:
        json_instruction = (
            "\n\nRespond ONLY with valid JSON. Do not include any explanation or "
            "markdown fences — output the JSON object directly."
        )
        system_text = (system_text + json_instruction).strip()

    # Clamp temperature to Anthropic's accepted range [0, 1]
    clamped_temperature = max(0.0, min(1.0, temperature))

    # Build the create() kwargs
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": filtered_messages,
        "temperature": clamped_temperature,
    }
    if system_text:
        kwargs["system"] = system_text

    # Enable extended thinking for supported models
    use_thinking = _anthropic_model_supports_thinking(model)
    if use_thinking:
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": _anthropic_thinking_budget(max_tokens)}
        # Anthropic requires temperature=1 when thinking is enabled
        kwargs["temperature"] = 1.0

    max_retries = 3
    backoff_delays = [1, 2, 4]

    for attempt in range(1, max_retries + 1):
        try:
            client = _anthropic.AsyncAnthropic(api_key=api_key)
            message = await client.messages.create(**kwargs)
            return _anthropic_response_to_oai(message)

        except Exception as exc:
            exc_type = type(exc).__name__
            # Check for retryable error types by name (avoids importing all sub-exceptions)
            is_retryable = any(
                name in exc_type
                for name in ("RateLimitError", "InternalServerError", "APIStatusError", "Timeout")
            )
            if is_retryable and attempt < max_retries:
                delay = backoff_delays[attempt - 1]
                logger.warning(
                    "Anthropic request attempt %d/%d failed (%s) for agent '%s'. "
                    "Retrying in %ds...",
                    attempt, max_retries, exc_type, agent_name, delay,
                )
                await asyncio.sleep(delay)
                continue
            elif is_retryable:
                logger.error(
                    "Anthropic request failed after %d attempts (%s) for agent '%s'.",
                    max_retries, exc_type, agent_name,
                )
                return _fallback_response(agent_name)
            else:
                # Non-retryable (AuthenticationError, BadRequestError, etc.) — re-raise
                logger.error(
                    "Anthropic non-retryable error (%s) for agent '%s': %s",
                    exc_type, agent_name, str(exc)[:200],
                )
                raise

    return _fallback_response(agent_name)


async def _anthropic_stream_completion(
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> AsyncIterator[dict]:
    """
    Native Anthropic SDK streaming path for ``stream_completion_with_thinking()``.

    Yields the same event dicts as the OAI streaming path:
        {"type": "thinking_token", "delta": "..."}
        {"type": "content_token",  "delta": "..."}
        {"type": "done", "thinking": str, "content": str}
    """
    try:
        import anthropic as _anthropic
    except ImportError:
        logger.error("The 'anthropic' package is not installed.")
        yield {
            "type": "done",
            "thinking": "",
            "content": "*Agent is temporarily unavailable — anthropic package missing.*",
        }
        return

    system_text, filtered_messages = _extract_system_from_messages(messages)
    clamped_temperature = max(0.0, min(1.0, temperature))

    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": filtered_messages,
        "temperature": clamped_temperature,
    }
    if system_text:
        kwargs["system"] = system_text

    use_thinking = _anthropic_model_supports_thinking(model)
    if use_thinking:
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": _anthropic_thinking_budget(max_tokens)}
        kwargs["temperature"] = 1.0

    max_retries = 3
    backoff_delays = [1, 2, 4]

    for attempt in range(1, max_retries + 1):
        full_thinking: list[str] = []
        full_content: list[str] = []
        try:
            client = _anthropic.AsyncAnthropic(api_key=api_key)
            async with client.messages.stream(**kwargs) as stream:
                async for event in stream:
                    event_type = getattr(event, "type", "")

                    if event_type == "content_block_start":
                        # block_start carries the initial block (could be thinking or text)
                        block = getattr(event, "content_block", None)
                        if block and getattr(block, "type", "") == "thinking":
                            # No delta yet — thinking text comes in content_block_delta
                            pass

                    elif event_type == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        if delta is None:
                            continue
                        delta_type = getattr(delta, "type", "")

                        if delta_type == "thinking_delta":
                            text = getattr(delta, "thinking", "") or ""
                            if text:
                                full_thinking.append(text)
                                yield {"type": "thinking_token", "delta": text}

                        elif delta_type == "text_delta":
                            text = getattr(delta, "text", "") or ""
                            if text:
                                full_content.append(text)
                                yield {"type": "content_token", "delta": text}

            yield {
                "type": "done",
                "thinking": "".join(full_thinking),
                "content": "".join(full_content),
            }
            return  # success

        except Exception as exc:
            exc_type = type(exc).__name__
            is_retryable = any(
                name in exc_type
                for name in ("RateLimitError", "InternalServerError", "APIStatusError", "Timeout")
            )
            if is_retryable and attempt < max_retries:
                delay = backoff_delays[attempt - 1]
                logger.warning(
                    "Anthropic streaming attempt %d/%d failed (%s). Retrying in %ds...",
                    attempt, max_retries, exc_type, delay,
                )
                await asyncio.sleep(delay)
                continue
            else:
                logger.error("Anthropic streaming failed (%s): %s", exc_type, str(exc)[:200])
                yield {
                    "type": "done",
                    "thinking": "",
                    "content": (
                        f"*Agent is temporarily unavailable — "
                        f"Anthropic error after {attempt} attempt(s).*"
                    ),
                }
                return


# ---------------------------------------------------------------------------
# Public API — OAI-compatible path (used for all non-Anthropic providers)
# ---------------------------------------------------------------------------

async def chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 1024,
    json_mode: bool = False,
    agent_name: str = "unknown",
) -> dict:
    """
    Send a chat completion request.

    Routes to the native Anthropic SDK when *base_url* points to
    ``api.anthropic.com``; otherwise uses the generic OAI-compatible httpx path.

    Returns the full response dict. Retries on transient errors (429, 5xx, timeout)
    up to 3 attempts with exponential backoff. Raises on permanent errors (400, 401).
    """
    # --- Anthropic native path ---
    if _is_anthropic_url(base_url):
        return await _anthropic_chat_completion(
            api_key=api_key,
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
            agent_name=agent_name,
        )

    # --- OAI-compatible path ---
    url = f"{base_url.rstrip('/')}/chat/completions"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    logger.debug("LLM request: model=%s, messages=%d, temp=%.1f", model, len(messages), temperature)

    max_retries = 3
    backoff_delays = [1, 2, 4]  # exponential backoff: 1s, 2s, 4s

    # Per-request client — avoids stale connection pool on Windows ProactorEventLoop (Bug B-2)
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        for attempt in range(1, max_retries + 1):
            try:
                resp = await client.post(url, json=payload, headers=headers)

                # Non-retryable client errors — raise immediately
                if resp.status_code in (400, 401):
                    resp.raise_for_status()

                # Retryable server/rate-limit errors
                if resp.status_code in _RETRYABLE_STATUS_CODES:
                    if attempt < max_retries:
                        delay = backoff_delays[attempt - 1]
                        logger.warning(
                            "LLM request attempt %d/%d failed (HTTP %d) for agent '%s'. Retrying in %ds...",
                            attempt, max_retries, resp.status_code, agent_name, delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(
                            "LLM request failed after %d attempts (HTTP %d) for agent '%s'.",
                            max_retries, resp.status_code, agent_name,
                        )
                        return _fallback_response(agent_name)

                resp.raise_for_status()
                data = resp.json()
                return data

            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                exc_name = "connection error" if isinstance(exc, httpx.ConnectError) else "timeout"
                if attempt < max_retries:
                    delay = backoff_delays[attempt - 1]
                    logger.warning(
                        "LLM request attempt %d/%d %s for agent '%s'. Retrying in %ds...",
                        attempt, max_retries, exc_name, agent_name, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        "LLM request %s after %d attempts for agent '%s'.",
                        exc_name, max_retries, agent_name,
                    )
                    return _fallback_response(agent_name)

            except httpx.HTTPStatusError:
                # Re-raise non-retryable HTTP errors (400, 401)
                raise

    # Should not reach here, but just in case
    return _fallback_response(agent_name)


def _fallback_response(agent_name: str) -> dict:
    """Return a fallback response dict matching the OAI chat completion format."""
    fallback_content = (
        f"*{agent_name} considered the discussion but chose to remain silent this turn.*\n\n"
        f"_(Agent temporarily unavailable — connection error after 3 attempts)_"
    )
    return {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": fallback_content,
            },
            "finish_reason": "error",
        }],
        "model": "fallback",
        "_is_fallback": True,
    }


async def get_completion_content(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 1024,
    json_mode: bool = False,
    agent_name: str = "unknown",
) -> str:
    """Convenience: returns just the assistant message content string."""
    data = await chat_completion(
        base_url=base_url,
        api_key=api_key,
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=json_mode,
        agent_name=agent_name,
    )
    # If response is a fallback (connection error), propagate it so callers can detect failure
    if data.get("_is_fallback") or data.get("model") == "fallback":
        choices = data.get("choices") or []
        if choices:
            return choices[0]["message"].get("content", "")
        return ""
    choices = data.get("choices") or []
    if not choices:
        logger.error("LLM response has no choices for agent '%s': %s", agent_name, str(data)[:200])
        return ""
    msg = choices[0].get("message", {})
    raw = msg.get("content", "")
    # Native Anthropic returns content as a list of typed blocks — flatten to string
    if isinstance(raw, list):
        _, content_text = _extract_thinking_from_response(data, model)
        raw = content_text or ""
    # Reasoning-model fallback: kimi, deepseek-r1 etc. may put output in 'reasoning'
    if not raw or not raw.strip():
        reasoning = msg.get("reasoning", "")
        if reasoning and reasoning.strip():
            logger.info("get_completion_content: using reasoning field as content for agent '%s'", agent_name)
            return reasoning
    return raw if raw else ""


async def get_completion_json(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.0,
    max_tokens: int = 1024,
    agent_name: str = "unknown",
) -> dict:
    """Convenience: returns parsed JSON from a JSON-mode completion. Falls back to plain mode."""

    def _try_parse(content: str) -> dict | None:
        """Try all parse strategies; return dict on success, None on failure."""
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        # Markdown fence stripping
        stripped = content.strip()
        if stripped.startswith("```"):
            lines = stripped.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            try:
                return json.loads("\n".join(lines))
            except json.JSONDecodeError:
                pass
        # Regex extraction — find outermost balanced JSON object
        start = content.find('{')
        if start != -1:
            # Try from start to last } (greedy match covers most cases)
            end = content.rfind('}')
            if end > start:
                try:
                    return json.loads(content[start:end + 1])
                except json.JSONDecodeError:
                    pass
            # Truncated JSON: try appending closing brace/brackets to salvage
            truncated = content[start:]
            for suffix in ("}", "]}", "}]}", "\n}"):
                try:
                    return json.loads(truncated + suffix)
                except json.JSONDecodeError:
                    pass
        return None

    # Attempt 1: with JSON mode
    content = await get_completion_content(
        base_url=base_url, api_key=api_key, model=model,
        messages=messages, temperature=temperature, max_tokens=max_tokens,
        json_mode=True, agent_name=agent_name,
    )
    result = _try_parse(content)
    if result is not None:
        return result

    # Attempt 2: without JSON mode (provider may not support response_format)
    logger.warning("JSON mode parse failed for '%s', retrying without json_mode", agent_name)
    content2 = await get_completion_content(
        base_url=base_url, api_key=api_key, model=model,
        messages=messages, temperature=temperature, max_tokens=max_tokens,
        json_mode=False, agent_name=agent_name,
    )
    result2 = _try_parse(content2)
    if result2 is not None:
        return result2

    logger.error("JSON parse failed (both modes) for '%s': %.200s", agent_name, content2)
    return {}


# ---------------------------------------------------------------------------
# Thinking / Reasoning Token Support
# ---------------------------------------------------------------------------

def _extract_thinking_from_response(data: dict, model: str) -> tuple[str, str]:
    """
    Extract thinking tokens and content from a non-streaming LLM response dict.

    Supports:
      - Anthropic-style: message.content is a list with blocks of type "thinking"
        or a top-level "reasoning_content" field on the message.
      - OpenAI o1/o3-style: message.reasoning_content field.

    Returns:
        (thinking_text, content_text)
    """
    thinking_parts: list[str] = []
    content_parts: list[str] = []

    choices = data.get("choices", [])
    if not choices:
        return "", ""

    message = choices[0].get("message", {})

    # Anthropic-style: content is a list of typed blocks
    raw_content = message.get("content")
    if isinstance(raw_content, list):
        for block in raw_content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")
            if block_type == "thinking":
                thinking_parts.append(block.get("thinking", "") or block.get("text", ""))
            else:
                # text, tool_use, etc. — take text field as content
                content_parts.append(block.get("text", "") or block.get("content", ""))
        thinking_text = "".join(thinking_parts)
        content_text = "".join(content_parts)
        return thinking_text, content_text

    # Anthropic-style: separate reasoning_content field
    if "reasoning_content" in message:
        thinking_text = message.get("reasoning_content") or ""
        content_text = raw_content if isinstance(raw_content, str) else ""
        return thinking_text, content_text

    # OpenAI o1/o3-style: reasoning_content field or model prefix detection
    is_reasoning_model = any(
        model.startswith(prefix) for prefix in ("o1", "o3", "o1-", "o3-")
    )
    if is_reasoning_model or "reasoning_content" in message:
        thinking_text = message.get("reasoning_content") or ""
        content_text = raw_content if isinstance(raw_content, str) else ""
        return thinking_text, content_text

    # No thinking tokens detected
    content_text = raw_content if isinstance(raw_content, str) else ""
    return "", content_text


async def get_completion_with_thinking(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 1024,
    json_mode: bool = False,
) -> tuple[str, str, bool]:
    """
    Like get_completion_content(), but also returns thinking/reasoning tokens.

    Returns:
        (thinking_text, content_text, is_fallback)

        thinking_text — concatenated reasoning/thinking tokens (empty string if none)
        content_text  — the normal assistant content
        is_fallback   — True if the response was a fallback (LLM error)
    """
    data = await chat_completion(
        base_url=base_url,
        api_key=api_key,
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=json_mode,
    )
    is_fallback = data.get("_is_fallback", False) or data.get("model") == "fallback"
    thinking, content = _extract_thinking_from_response(data, model)
    return thinking, content, is_fallback


async def stream_completion_with_thinking(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> AsyncIterator[dict]:
    """
    Streaming variant of get_completion_with_thinking().

    Routes to the native Anthropic SDK when *base_url* points to
    ``api.anthropic.com``; otherwise uses the generic OAI-compatible SSE path.

    Yields dicts:
        {"type": "thinking_token", "delta": "..."}  — reasoning chunk
        {"type": "content_token", "delta": "..."}   — normal content chunk
        {"type": "done", "thinking": str, "content": str}  — final summary

    Supports:
      - Anthropic native streaming (thinking_delta / text_delta events)
      - Anthropic-style streaming via OAI proxy: chunks with type "thinking" in delta
        or delta.reasoning_content
      - OpenAI o1/o3-style: delta.reasoning_content field
    """
    # --- Anthropic native path ---
    if _is_anthropic_url(base_url):
        async for event in _anthropic_stream_completion(
            api_key=api_key,
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield event
        return

    # --- OAI-compatible SSE path ---
    url = f"{base_url.rstrip('/')}/chat/completions"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    logger.debug(
        "LLM streaming request (with thinking): model=%s, messages=%d",
        model,
        len(messages),
    )

    is_reasoning_model = any(
        model.startswith(prefix) for prefix in ("o1", "o3", "o1-", "o3-")
    )

    max_retries = 3
    backoff_delays = [1, 2, 4]  # exponential backoff: 1s, 2s, 4s (len must equal max_retries)

    for attempt in range(1, max_retries + 1):
        full_thinking: list[str] = []
        full_content: list[str] = []
        last_finish_reason: str = None  # #111: track finish_reason from LLM chunks
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client, \
                       client.stream("POST", url, json=payload, headers=headers) as response:
                # #189: retry on retryable HTTP status codes (429, 5xx) same as batch mode
                if response.status_code in _RETRYABLE_STATUS_CODES:
                    if attempt < max_retries:
                        delay = backoff_delays[attempt - 1]
                        logger.warning(
                            "LLM streaming HTTP %d (attempt %d/%d). Retrying in %ds...",
                            response.status_code, attempt, max_retries, delay,
                        )
                        # #138: clear frontend buffer before retry
                        yield {"type": "stream_reset"}
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(
                            "LLM streaming HTTP %d after %d attempts — giving up.",
                            response.status_code, max_retries,
                        )
                        yield {
                            "type": "done",
                            "thinking": "",
                            "content": f"*Agent unavailable — HTTP {response.status_code} after {max_retries} attempts.*",
                            "is_fallback": True,
                        }
                        return
                response.raise_for_status()

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue

                    data_str = line[len("data: "):]
                    if data_str == "[DONE]":
                        break

                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        logger.warning("Could not parse SSE chunk: %s", data_str[:200])
                        continue

                    choices = chunk.get("choices", [])
                    if not choices:
                        continue

                    choice = choices[0]
                    delta = choice.get("delta", {})
                    finish_reason = choice.get("finish_reason")

                    # Anthropic-style: delta has a "type" field = "thinking"
                    delta_type = delta.get("type", "")
                    if delta_type == "thinking":
                        text = delta.get("thinking", "") or delta.get("text", "") or ""
                        if text:
                            full_thinking.append(text)
                            yield {"type": "thinking_token", "delta": text}
                        if finish_reason:
                            break
                        continue

                    # OpenAI o1/o3-style, Anthropic reasoning_content, or
                    # Kimi/Ollama-style "reasoning" field in delta
                    reasoning_delta = (
                        delta.get("reasoning_content", "")
                        or delta.get("reasoning", "")
                    )
                    if reasoning_delta:
                        full_thinking.append(reasoning_delta)
                        yield {"type": "thinking_token", "delta": reasoning_delta}

                    # Normal content delta
                    content_delta = delta.get("content", "")
                    if content_delta:
                        full_content.append(content_delta)
                        yield {"type": "content_token", "delta": content_delta}

                    # Some providers (Ollama, NewAPI, etc.) signal completion via
                    # finish_reason="stop" without a [DONE] line. Break here to
                    # avoid hanging on aiter_lines() waiting for data that never comes.
                    if finish_reason in ("stop", "length", "end_turn"):
                        last_finish_reason = finish_reason  # #111: capture terminal finish_reason
                        break

            # #111: include finish_reason in done chunk so _agent_turn can detect truncation
            yield {
                "type": "done",
                "thinking": "".join(full_thinking),
                "content": "".join(full_content),
                "finish_reason": last_finish_reason,
            }
            return  # success — exit retry loop

        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            exc_name = "connection error" if isinstance(exc, httpx.ConnectError) else "timeout"
            if attempt < max_retries:
                delay = backoff_delays[attempt - 1]
                logger.warning(
                    "LLM streaming attempt %d/%d %s. Retrying in %ds...",
                    attempt, max_retries, exc_name, delay,
                )
                # #138: signal the engine to discard any partial tokens already yielded
                # from this attempt — prevents duplicate content in the frontend buffer.
                yield {"type": "stream_reset"}
                await asyncio.sleep(delay)
                continue
            else:
                logger.error(
                    "LLM streaming %s after %d attempts.",
                    exc_name, max_retries,
                )
                yield {
                    "type": "done",
                    "thinking": "",
                    "content": f"*Agent is temporarily unavailable — connection error after {max_retries} attempts.*",
                    "is_fallback": True,
                }
                return
