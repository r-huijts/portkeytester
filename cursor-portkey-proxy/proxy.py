import asyncio
import json
import logging
import os
import secrets
import time
from collections import Counter
from typing import Any, AsyncGenerator, Dict, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PORTKEY_URL = os.getenv("PORTKEY_URL", "https://api.portkey.ai/v1").rstrip("/")
PORTKEY_API_KEY = os.getenv("PORTKEY_API_KEY", "")
PROXY_API_KEY = os.getenv("PROXY_API_KEY", "")

CURSOR_MODEL = os.getenv("CURSOR_MODEL", "kimi-k2.7-code-portkey")
PORTKEY_MODEL = os.getenv("PORTKEY_MODEL", "kimi-k2.7-code")

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Keep real streaming enabled.
FORCE_NONSTREAM = False

# Send an SSE keepalive while waiting for upstream data.
KEEPALIVE_INTERVAL = float(os.getenv("KEEPALIVE_INTERVAL", "10"))

# Maximum time an upstream HTTP read may remain open.
UPSTREAM_TIMEOUT = float(os.getenv("UPSTREAM_TIMEOUT", "3600"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger("cursor-portkey-proxy")

# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(title="Cursor Portkey Proxy")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def request_id() -> str:
    return secrets.token_hex(6)


def short(value: Any, limit: int = 500) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"


def kb(value: int) -> float:
    return round(value / 1024, 1)


def json_size(value: Any) -> int:
    try:
        return len(
            json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    except Exception:
        return 0


def sse(data: Any) -> str:
    if isinstance(data, str):
        payload = data
    else:
        payload = json.dumps(
            data,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    return f"data: {payload}\n\n"


def make_stream_chunk(
    response_id: str,
    model: str,
    *,
    index: int = 0,
    delta: Optional[Dict[str, Any]] = None,
    finish_reason: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": index,
                "delta": delta or {},
                "finish_reason": finish_reason,
            }
        ],
    }


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def context_stats(body: Dict[str, Any]) -> Dict[str, Any]:
    messages = body.get("messages") or []

    roles = Counter(
        str(message.get("role", "unknown"))
        for message in messages
        if isinstance(message, dict)
    )

    sizes = []
    assistant_tool_messages = 0
    total_tool_calls = 0
    max_tools_in_message = 0

    content_types = Counter()

    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue

        size = json_size(message)
        sizes.append(
            (
                size,
                index,
                message.get("role"),
            )
        )

        tool_calls = message.get("tool_calls") or []

        if tool_calls:
            assistant_tool_messages += 1
            total_tool_calls += len(tool_calls)
            max_tools_in_message = max(
                max_tools_in_message,
                len(tool_calls),
            )

        content = message.get("content")

        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    content_types[str(item.get("type", "unknown"))] += 1

    largest = max(
        sizes,
        default=(0, None, None),
        key=lambda x: x[0],
    )

    return {
        "messages": len(messages),
        "messages_by_role": dict(roles),
        "request_kb": kb(json_size(body)),
        "bytes_by_role_kb": {
            role: kb(
                sum(
                    json_size(m)
                    for m in messages
                    if isinstance(m, dict)
                    and m.get("role") == role
                )
            )
            for role in roles
        },
        "average_message_kb": (
            round(json_size(body) / len(messages) / 1024, 1)
            if messages
            else 0
        ),
        "largest_message_kb": kb(largest[0]),
        "largest_message_role": largest[2],
        "largest_message_index": largest[1],
        "largest_message_chars": (
            len(json.dumps(messages[largest[1]], ensure_ascii=False))
            if largest[1] is not None
            else 0
        ),
        "assistant_messages_with_tools": assistant_tool_messages,
        "total_tool_calls": total_tool_calls,
        "max_tools_in_one_assistant_message": max_tools_in_message,
        "content_types": dict(content_types),
        "last_role": (
            messages[-1].get("role")
            if messages and isinstance(messages[-1], dict)
            else None
        ),
        "tools": len(body.get("tools") or []),
    }


def multimodal_stats(body: Dict[str, Any]) -> Dict[str, Any]:
    image_items = 0
    image_url_items = 0
    image_data_bytes = 0

    for message in body.get("messages") or []:
        if not isinstance(message, dict):
            continue

        content = message.get("content")

        if not isinstance(content, list):
            continue

        for item in content:
            if not isinstance(item, dict):
                continue

            item_type = item.get("type")

            if item_type == "image_url":
                image_items += 1
                image_url_items += 1

                image_url = item.get("image_url")

                if isinstance(image_url, dict):
                    url = image_url.get("url", "")

                    if isinstance(url, str) and url.startswith("data:"):
                        image_data_bytes += len(url.encode("utf-8"))

            elif item_type == "image":
                image_items += 1

    return {
        "image_items": image_items,
        "image_url_items": image_url_items,
        "image_data_mb": round(
            image_data_bytes / 1024 / 1024,
            2,
        ),
    }


def tool_history_stats(body: Dict[str, Any]) -> Dict[str, Any]:
    assistant_calls = []
    tool_results = []

    for message in body.get("messages") or []:
        if not isinstance(message, dict):
            continue

        if message.get("role") == "assistant":
            for call in message.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue

                function = call.get("function") or {}

                assistant_calls.append(
                    {
                        "id": call.get("id"),
                        "name": function.get("name"),
                    }
                )

        elif message.get("role") == "tool":
            tool_results.append(
                {
                    "tool_call_id": message.get("tool_call_id"),
                    "name": message.get("name"),
                }
            )

    call_ids = [
        item["id"]
        for item in assistant_calls
        if item.get("id")
    ]

    result_ids = [
        item["tool_call_id"]
        for item in tool_results
        if item.get("tool_call_id")
    ]

    call_counter = Counter(call_ids)
    result_counter = Counter(result_ids)

    unmatched = [
        call_id
        for call_id in call_ids
        if call_id not in result_counter
    ]

    orphan = [
        result_id
        for result_id in result_ids
        if result_id not in call_counter
    ]

    duplicates = [
        call_id
        for call_id, count in call_counter.items()
        if count > 1
    ]

    return {
        "assistant_tool_calls": len(assistant_calls),
        "tool_results": len(tool_results),
        "unmatched_tool_calls": len(unmatched),
        "orphan_tool_results": len(orphan),
        "duplicate_tool_call_ids": len(duplicates),
    }


def tool_calls_by_name(body: Dict[str, Any]) -> Dict[str, int]:
    counts = Counter()

    for message in body.get("messages") or []:
        if not isinstance(message, dict):
            continue

        if message.get("role") != "assistant":
            continue

        for call in message.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue

            function = call.get("function") or {}
            name = function.get("name")

            if name:
                counts[name] += 1

    return dict(counts)


def tool_context_stats(body: Dict[str, Any]) -> Dict[str, Any]:
    results = []

    for index, message in enumerate(body.get("messages") or []):
        if not isinstance(message, dict):
            continue

        if message.get("role") != "tool":
            continue

        content = message.get("content", "")
        size = json_size(content)

        results.append(
            {
                "tool": message.get("name") or "unknown",
                "kb": kb(size),
                "index": index,
            }
        )

    if not results:
        return {
            "result_messages": 0,
            "result_kb": 0,
            "average_result_kb": 0,
            "largest_result_kb": 0,
            "largest_result_tool": None,
            "largest_result_index": None,
            "by_tool": {},
            "top_5_results": [],
        }

    largest = max(
        results,
        key=lambda x: x["kb"],
    )

    by_tool: Dict[str, Dict[str, Any]] = {}

    for item in results:
        tool = item["tool"]

        if tool not in by_tool:
            by_tool[tool] = {
                "calls": 0,
                "result_kb": 0,
                "average_kb": 0,
                "largest_kb": 0,
                "largest_result_index": None,
            }

        entry = by_tool[tool]

        entry["calls"] += 1
        entry["result_kb"] += item["kb"]

        if item["kb"] > entry["largest_kb"]:
            entry["largest_kb"] = item["kb"]
            entry["largest_result_index"] = item["index"]

    for entry in by_tool.values():
        entry["result_kb"] = round(entry["result_kb"], 1)
        entry["average_kb"] = round(
            entry["result_kb"] / entry["calls"],
            1,
        )

    top_5 = sorted(
        results,
        key=lambda x: x["kb"],
        reverse=True,
    )[:5]

    return {
        "result_messages": len(results),
        "result_kb": round(
            sum(item["kb"] for item in results),
            1,
        ),
        "average_result_kb": round(
            sum(item["kb"] for item in results) / len(results),
            1,
        ),
        "largest_result_kb": largest["kb"],
        "largest_result_tool": largest["tool"],
        "largest_result_index": largest["index"],
        "by_tool": by_tool,
        "top_5_results": top_5,
    }


def response_tool_stats(response: Dict[str, Any]) -> Dict[str, Any]:
    tool_calls = []
    tool_names = []

    for choice in response.get("choices") or []:
        message = choice.get("message") or {}

        for call in message.get("tool_calls") or []:
            tool_calls.append(call)

            function = call.get("function") or {}
            name = function.get("name")

            if name:
                tool_names.append(name)

    usage = response.get("usage") or {}

    return {
        "choices": len(response.get("choices") or []),
        "tool_calls": len(tool_calls),
        "tool_names": tool_names,
        "finish_reasons": [
            choice.get("finish_reason")
            for choice in response.get("choices") or []
        ],
        "content_chars": sum(
            len(
                str(
                    (choice.get("message") or {}).get(
                        "content"
                    )
                    or ""
                )
            )
            for choice in response.get("choices") or []
        ),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def check_proxy_auth(authorization: Optional[str]) -> None:
    if not PROXY_API_KEY:
        return

    expected = f"Bearer {PROXY_API_KEY}"

    if authorization != expected:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )


# ---------------------------------------------------------------------------
# Portkey headers
# ---------------------------------------------------------------------------

def portkey_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {PORTKEY_API_KEY}",
        "Content-Type": "application/json",
        "x-portkey-api-key": PORTKEY_API_KEY,
    }


# ---------------------------------------------------------------------------
# Non-streaming request
# ---------------------------------------------------------------------------

async def call_portkey(
    body: Dict[str, Any],
    rid: str,
) -> httpx.Response:

    timeout = httpx.Timeout(
        connect=30.0,
        read=UPSTREAM_TIMEOUT,
        write=30.0,
        pool=30.0,
    )

    url = f"{PORTKEY_URL}/chat/completions"

    logger.info(
        "PORTKEY_REQUEST id=%s stream=%s model=%s",
        rid,
        body.get("stream"),
        body.get("model"),
    )

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            url,
            headers=portkey_headers(),
            json=body,
        )

        logger.info(
            "PORTKEY_RESPONSE id=%s status=%s bytes=%s",
            rid,
            response.status_code,
            len(response.content),
        )

        if response.status_code >= 400:
            logger.error(
                "PORTKEY_ERROR id=%s status=%s body=%s",
                rid,
                response.status_code,
                short(response.text, 1500),
            )

        return response


# ---------------------------------------------------------------------------
# Streaming Portkey request
# ---------------------------------------------------------------------------

async def stream_portkey(
    body: Dict[str, Any],
    rid: str,
) -> AsyncGenerator[str, None]:

    timeout = httpx.Timeout(
        connect=30.0,
        read=UPSTREAM_TIMEOUT,
        write=30.0,
        pool=30.0,
    )

    url = f"{PORTKEY_URL}/chat/completions"

    response_id = f"chatcmpl-{secrets.token_hex(8)}"

    events = 0
    bytes_received = 0
    text_chunks = 0
    tool_call_count = 0

    saw_done = False
    saw_finish_reason = False

    finish_reason: Optional[str] = None

    tool_calls: Dict[int, Dict[str, Any]] = {}

    logger.info(
        "PORTKEY_STREAM START id=%s model=%s",
        rid,
        body.get("model"),
    )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:

            try:
                async with client.stream(
                    "POST",
                    url,
                    headers=portkey_headers(),
                    json=body,
                ) as response:

                    logger.info(
                        "PORTKEY_STREAM CONNECTED id=%s status=%s",
                        rid,
                        response.status_code,
                    )

                    relevant_headers = {}

                    for key, value in response.headers.items():
                        lower = key.lower()

                        if any(
                            part in lower
                            for part in (
                                "portkey",
                                "request-id",
                                "trace",
                                "provider",
                                "model",
                                "error",
                                "gateway",
                                "retry",
                            )
                        ):
                            relevant_headers[key] = value

                    if relevant_headers:
                        logger.info(
                            "PORTKEY_HEADERS id=%s headers=%s",
                            rid,
                            relevant_headers,
                        )

                    if response.status_code >= 400:
                        error_body = await response.aread()

                        logger.error(
                            "PORTKEY_STREAM ERROR id=%s status=%s body=%s",
                            rid,
                            response.status_code,
                            short(
                                error_body.decode(
                                    "utf-8",
                                    errors="replace",
                                ),
                                1500,
                            ),
                        )

                        error_payload = {
                            "error": {
                                "message": (
                                    "Portkey upstream returned "
                                    f"HTTP {response.status_code}"
                                ),
                                "type": "upstream_error",
                                "status": response.status_code,
                            }
                        }

                        yield sse(error_payload)
                        yield sse("[DONE]")

                        return

                    logger.info(
                        "PORTKEY_STREAM HTTP OK id=%s",
                        rid,
                    )

                    # -------------------------------------------------------
                    # Parse SSE events
                    # -------------------------------------------------------

                    data_lines = []

                    async for line in response.aiter_lines():

                        if line.startswith("data:"):
                            data_lines.append(
                                line[5:].lstrip()
                            )
                            continue

                        # SSE event ends on an empty line.
                        if line != "":
                            continue

                        if not data_lines:
                            continue

                        raw_data = "\n".join(data_lines)
                        data_lines.clear()

                        events += 1
                        bytes_received += len(
                            raw_data.encode("utf-8")
                        )

                        if raw_data == "[DONE]":
                            saw_done = True

                            logger.info(
                                "PORTKEY_STREAM DONE id=%s",
                                rid,
                            )

                            break

                        try:
                            event = json.loads(raw_data)

                        except json.JSONDecodeError:
                            logger.warning(
                                "PORTKEY_STREAM INVALID_JSON "
                                "id=%s data=%s",
                                rid,
                                short(raw_data),
                            )
                            continue

                        choices = event.get("choices") or []

                        for choice in choices:

                            delta = choice.get("delta") or {}

                            current_finish = choice.get(
                                "finish_reason"
                            )

                            if current_finish is not None:
                                finish_reason = current_finish
                                saw_finish_reason = True

                            # ------------------------------------------------
                            # Normal text delta
                            # ------------------------------------------------

                            content = delta.get("content")

                            if content:
                                text_chunks += 1

                                yield sse(
                                    make_stream_chunk(
                                        response_id,
                                        CURSOR_MODEL,
                                        index=choice.get(
                                            "index",
                                            0,
                                        ),
                                        delta={
                                            "content": content
                                        },
                                        finish_reason=None,
                                    )
                                )

                            # ------------------------------------------------
                            # Tool calls
                            # ------------------------------------------------

                            incoming_tool_calls = (
                                delta.get("tool_calls") or []
                            )

                            for incoming in incoming_tool_calls:

                                index = incoming.get(
                                    "index",
                                    0,
                                )

                                if index not in tool_calls:
                                    tool_calls[index] = {
                                        "id": None,
                                        "type": "function",
                                        "name": "",
                                        "arguments": "",
                                    }

                                stored = tool_calls[index]

                                if incoming.get("id"):
                                    stored["id"] = incoming["id"]

                                if incoming.get("type"):
                                    stored["type"] = incoming["type"]

                                function = (
                                    incoming.get("function")
                                    or {}
                                )

                                if function.get("name"):
                                    stored["name"] += (
                                        function["name"]
                                    )

                                if function.get("arguments"):
                                    stored["arguments"] += (
                                        function["arguments"]
                                    )

                            # ------------------------------------------------
                            # When the model tells us the tool calls are
                            # complete, emit them as complete synthetic
                            # OpenAI-compatible chunks.
                            # ------------------------------------------------

                            if (
                                current_finish == "tool_calls"
                                and tool_calls
                            ):

                                tool_call_count = len(tool_calls)

                                names = [
                                    item["name"]
                                    for item in tool_calls.values()
                                ]

                                logger.info(
                                    "PORTKEY_STREAM TOOL_CALLS "
                                    "id=%s count=%s names=%s",
                                    rid,
                                    tool_call_count,
                                    names,
                                )

                                for index, tool in sorted(
                                    tool_calls.items()
                                ):

                                    logger.info(
                                        "PORTKEY_STREAM TOOL "
                                        "id=%s index=%s name=%s "
                                        "args_kb=%s",
                                        rid,
                                        index,
                                        tool["name"],
                                        kb(
                                            len(
                                                tool[
                                                    "arguments"
                                                ].encode("utf-8")
                                            )
                                        ),
                                    )

                                    # First chunk: tool metadata.
                                    yield sse(
                                        make_stream_chunk(
                                            response_id,
                                            CURSOR_MODEL,
                                            index=choice.get(
                                                "index",
                                                0,
                                            ),
                                            delta={
                                                "tool_calls": [
                                                    {
                                                        "index": index,
                                                        "id": tool["id"],
                                                        "type": "function",
                                                        "function": {
                                                            "name": tool[
                                                                "name"
                                                            ],
                                                        },
                                                    }
                                                ]
                                            },
                                            finish_reason=None,
                                        )
                                    )

                                    # Second chunk: complete arguments.
                                    yield sse(
                                        make_stream_chunk(
                                            response_id,
                                            CURSOR_MODEL,
                                            index=choice.get(
                                                "index",
                                                0,
                                            ),
                                            delta={
                                                "tool_calls": [
                                                    {
                                                        "index": index,
                                                        "function": {
                                                            "arguments": tool[
                                                                "arguments"
                                                            ]
                                                        },
                                                    }
                                                ]
                                            },
                                            finish_reason=None,
                                        )
                                    )

                                # Prevent duplicate emission if upstream sends
                                # another event carrying the same finish reason.
                                tool_calls.clear()

                        # Do not emit a finish chunk yet.
                        #
                        # We wait until we know whether the upstream stream
                        # actually terminated correctly.
                        #
                        # This is important because an upstream connection
                        # can close without a finish_reason.
                        #
                        # Previously we converted finish=None into "stop",
                        # which falsely told Cursor that the response had
                        # completed successfully.

                    # -------------------------------------------------------
                    # End of upstream stream
                    # -------------------------------------------------------

                    if not saw_done and saw_finish_reason:
                        logger.warning(
                            "PORTKEY_STREAM "
                            "UPSTREAM_CLOSED_WITHOUT_DONE "
                            "id=%s events=%s bytes=%s finish=%s",
                            rid,
                            events,
                            bytes_received,
                            finish_reason,
                        )

                    elif not saw_done and not saw_finish_reason:
                        logger.warning(
                            "PORTKEY_STREAM "
                            "UPSTREAM_CLOSED_WITHOUT_DONE "
                            "id=%s events=%s bytes=%s finish=None",
                            rid,
                            events,
                            bytes_received,
                        )

                    # -------------------------------------------------------
                    # IMPORTANT CHANGE:
                    #
                    # Only emit a final finish chunk when Portkey actually
                    # supplied a finish_reason.
                    #
                    # If the connection simply vanished without a finish
                    # reason, DO NOT manufacture "stop".
                    # -------------------------------------------------------

                    if saw_finish_reason and finish_reason:

                        yield sse(
                            make_stream_chunk(
                                response_id,
                                CURSOR_MODEL,
                                delta={},
                                finish_reason=finish_reason,
                            )
                        )

                    elif not saw_finish_reason:

                        logger.warning(
                            "PORTKEY_STREAM INCOMPLETE "
                            "id=%s events=%s bytes=%s "
                            "saw_done=%s saw_finish=%s",
                            rid,
                            events,
                            bytes_received,
                            saw_done,
                            saw_finish_reason,
                        )

                        # Do not send a fake finish_reason.
                        #
                        # Cursor will see the SSE connection terminate
                        # without a completion chunk instead of being told
                        # that the model successfully stopped.

                    # [DONE] is still sent when the upstream supplied a
                    # normal completion or when we explicitly saw [DONE].
                    #
                    # For a genuinely incomplete upstream response we don't
                    # manufacture completion semantics.
                    if saw_done or saw_finish_reason:
                        yield sse("[DONE]")

            except httpx.TimeoutException as exc:
                logger.error(
                    "PORTKEY_STREAM_TIMEOUT id=%s error=%s",
                    rid,
                    short(exc),
                )

            except httpx.RequestError as exc:
                logger.error(
                    "PORTKEY_STREAM_REQUEST_ERROR "
                    "id=%s error=%s",
                    rid,
                    short(exc),
                )

            except asyncio.CancelledError:
                logger.info(
                    "PORTKEY_STREAM CANCELLED id=%s",
                    rid,
                )
                raise

            except Exception as exc:
                logger.exception(
                    "PORTKEY_STREAM_EXCEPTION id=%s error=%s",
                    rid,
                    short(exc),
                )

    finally:
        logger.info(
            "PORTKEY_STREAM END "
            "id=%s events=%s bytes=%s text_chunks=%s "
            "tool_calls=%s finish=%s saw_done=%s "
            "saw_finish=%s",
            rid,
            events,
            bytes_received,
            text_chunks,
            tool_call_count,
            finish_reason,
            saw_done,
            saw_finish_reason,
        )


# ---------------------------------------------------------------------------
# Streaming wrapper with keepalive
# ---------------------------------------------------------------------------

async def streaming_response_generator(
    body: Dict[str, Any],
    rid: str,
) -> AsyncGenerator[str, None]:

    queue: asyncio.Queue = asyncio.Queue()

    async def producer() -> None:
        try:
            async for item in stream_portkey(body, rid):
                await queue.put(
                    (
                        "data",
                        item,
                    )
                )

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            logger.exception(
                "STREAM_PRODUCER_EXCEPTION id=%s error=%s",
                rid,
                short(exc),
            )

        finally:
            await queue.put(
                (
                    "done",
                    None,
                )
            )

    task = asyncio.create_task(
        producer(),
        name=f"portkey-stream-{rid}",
    )

    try:
        while True:

            try:
                event_type, value = await asyncio.wait_for(
                    queue.get(),
                    timeout=KEEPALIVE_INTERVAL,
                )

            except asyncio.TimeoutError:

                keepalive_id = secrets.token_hex(6)

                logger.info(
                    "STREAM_KEEPALIVE id=%s",
                    keepalive_id,
                )

                yield sse(
                    {
                        "id": "keepalive",
                        "object": "chat.completion.chunk",
                        "choices": [],
                    }
                )

                continue

            if event_type == "done":
                break

            yield value

    except asyncio.CancelledError:
        logger.info(
            "STREAM_CLIENT_DISCONNECTED id=%s",
            rid,
        )

        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        raise

    finally:
        if not task.done():
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "model": CURSOR_MODEL,
        "upstream_model": PORTKEY_MODEL,
        "upstream_url": PORTKEY_URL,
        "force_nonstream": FORCE_NONSTREAM,
        "streaming": not FORCE_NONSTREAM,
        "keepalive_interval": KEEPALIVE_INTERVAL,
        "upstream_timeout": UPSTREAM_TIMEOUT,
    }


# ---------------------------------------------------------------------------
# /v1/models
# ---------------------------------------------------------------------------

@app.get("/v1/models")
async def models(
    authorization: Optional[str] = Header(default=None),
):
    check_proxy_auth(authorization)

    return {
        "object": "list",
        "data": [
            {
                "id": CURSOR_MODEL,
                "object": "model",
                "owned_by": "portkey",
            }
        ],
    }


# ---------------------------------------------------------------------------
# /v1/chat/completions
# ---------------------------------------------------------------------------

@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    authorization: Optional[str] = Header(default=None),
):

    check_proxy_auth(authorization)

    rid = request_id()

    try:
        body = await request.json()

    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON",
        )

    # ---------------------------------------------------------------
    # Force the model that Portkey should receive.
    # ---------------------------------------------------------------

    original_model = body.get("model")

    body["model"] = PORTKEY_MODEL

    requested_stream = bool(body.get("stream", False))

    if FORCE_NONSTREAM:
        requested_stream = False

    # ---------------------------------------------------------------
    # Diagnostics
    # ---------------------------------------------------------------

    stats = context_stats(body)
    multimodal = multimodal_stats(body)
    history = tool_history_stats(body)
    by_name = tool_calls_by_name(body)
    tool_context = tool_context_stats(body)

    logger.info(
        "REQUEST id=%s stream=%s messages=%s roles=%s "
        "request_kb=%s tools=%s tool_calls=%s tool_results=%s "
        "tool_result_kb=%s largest_tool_kb=%s largest_tool=%s",
        rid,
        requested_stream,
        stats["messages"],
        stats["messages_by_role"],
        stats["request_kb"],
        stats["tools"],
        stats["total_tool_calls"],
        history["tool_results"],
        tool_context["result_kb"],
        tool_context["largest_result_kb"],
        tool_context["largest_result_tool"],
    )

    logger.info(
        "REQUEST_DETAIL id=%s largest_message_kb=%s "
        "largest_role=%s largest_index=%s "
        "assistant_tool_messages=%s tools_by_name=%s "
        "multimodal=%s",
        rid,
        stats["largest_message_kb"],
        stats["largest_message_role"],
        stats["largest_message_index"],
        stats["assistant_messages_with_tools"],
        by_name,
        multimodal,
    )

    logger.info(
        "TOOL_CONTEXT id=%s result_messages=%s result_kb=%s "
        "average_result_kb=%s largest_result_kb=%s "
        "largest_tool=%s largest_index=%s top5=%s "
        "unmatched=%s orphan=%s duplicate_ids=%s",
        rid,
        tool_context["result_messages"],
        tool_context["result_kb"],
        tool_context["average_result_kb"],
        tool_context["largest_result_kb"],
        tool_context["largest_result_tool"],
        tool_context["largest_result_index"],
        tool_context["top_5_results"],
        history["unmatched_tool_calls"],
        history["orphan_tool_results"],
        history["duplicate_tool_call_ids"],
    )

    # ---------------------------------------------------------------
    # Upstream request
    # ---------------------------------------------------------------

    body["stream"] = requested_stream

    if requested_stream:
        logger.info(
            "STREAM_REQUEST id=%s upstream_stream=true",
            rid,
        )

        return StreamingResponse(
            streaming_response_generator(
                body,
                rid,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ---------------------------------------------------------------
    # Normal non-streaming request
    # ---------------------------------------------------------------

    logger.info(
        "NONSTREAM_REQUEST id=%s upstream_stream=false",
        rid,
    )

    response = await call_portkey(
        body,
        rid,
    )

    if response.status_code >= 400:
        return JSONResponse(
            status_code=response.status_code,
            content={
                "error": {
                    "message": short(
                        response.text,
                        1500,
                    ),
                    "type": "upstream_error",
                    "status": response.status_code,
                }
            },
        )

    try:
        response_json = response.json()

    except Exception:
        logger.error(
            "PORTKEY_RESPONSE_INVALID_JSON id=%s body=%s",
            rid,
            short(response.text, 1500),
        )

        return JSONResponse(
            status_code=502,
            content={
                "error": {
                    "message": "Invalid JSON response from Portkey",
                    "type": "upstream_error",
                }
            },
        )

    logger.info(
        "RESPONSE_TOOL_STATS id=%s stats=%s",
        rid,
        response_tool_stats(response_json),
    )

    return JSONResponse(
        content=response_json,
    )


# ---------------------------------------------------------------------------
# Startup diagnostics
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup() -> None:

    if not PORTKEY_API_KEY:
        logger.warning(
            "PORTKEY_API_KEY is not configured"
        )

    if not PROXY_API_KEY:
        logger.warning(
            "PROXY_API_KEY is not configured; "
            "proxy authentication is disabled"
        )

    logger.info(
        "Proxy started "
        "listen=%s:%s "
        "cursor_model=%s "
        "portkey_model=%s "
        "portkey_url=%s "
        "force_nonstream=%s "
        "keepalive=%s "
        "timeout=%s",
        HOST,
        PORT,
        CURSOR_MODEL,
        PORTKEY_MODEL,
        PORTKEY_URL,
        FORCE_NONSTREAM,
        KEEPALIVE_INTERVAL,
        UPSTREAM_TIMEOUT,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
    )
