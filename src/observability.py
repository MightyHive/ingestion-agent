"""Local console observability for the agent platform."""

from __future__ import annotations

from time import perf_counter
from typing import Any, Callable, Dict

_OBSERVABILITY_ENABLED = False


def set_observability_enabled(enabled: bool) -> None:
    """Enable or disable local observability logs."""
    global _OBSERVABILITY_ENABLED
    _OBSERVABILITY_ENABLED = enabled


def is_observability_enabled() -> bool:
    """Whether local observability is active."""
    return _OBSERVABILITY_ENABLED


def empty_usage() -> Dict[str, int]:
    """Baseline structure for token usage aggregation."""
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def merge_usage(acc: Dict[str, int], usage: Dict[str, int] | None) -> Dict[str, int]:
    """Add partial usage into an accumulator."""
    out = dict(acc or empty_usage())
    incoming = usage or empty_usage()
    out["prompt_tokens"] = int(out.get("prompt_tokens", 0)) + int(incoming.get("prompt_tokens", 0))
    out["completion_tokens"] = int(out.get("completion_tokens", 0)) + int(incoming.get("completion_tokens", 0))
    out["total_tokens"] = int(out.get("total_tokens", 0)) + int(incoming.get("total_tokens", 0))
    return out


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _merge_usage_max(base: Dict[str, int], other: Dict[str, int]) -> Dict[str, int]:
    """
    Merge usage by per-field max to avoid double counting
    when the same data appears under different aliases.
    """
    return {
        "prompt_tokens": max(int(base.get("prompt_tokens", 0)), int(other.get("prompt_tokens", 0))),
        "completion_tokens": max(int(base.get("completion_tokens", 0)), int(other.get("completion_tokens", 0))),
        "total_tokens": max(int(base.get("total_tokens", 0)), int(other.get("total_tokens", 0))),
    }


def _first_int(mapping: Dict[str, Any], keys: tuple[str, ...]) -> int:
    for key in keys:
        if key in mapping and mapping.get(key) is not None:
            return _coerce_int(mapping.get(key))
    return 0


def _usage_from_mapping(mapping: Dict[str, Any], depth: int = 0) -> Dict[str, int]:
    if depth > 4:
        return empty_usage()

    prompt = _first_int(
        mapping,
        ("prompt_tokens", "prompt_token_count", "request_tokens", "input_tokens", "input_token_count"),
    )
    completion = _first_int(
        mapping,
        (
            "completion_tokens",
            "candidates_token_count",
            "response_tokens",
            "output_tokens",
            "output_token_count",
        ),
    )
    total = _first_int(mapping, ("total_tokens", "total_token_count"))

    usage = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }

    for nested_key in ("token_usage", "usage", "usage_metadata", "response_metadata"):
        nested = mapping.get(nested_key)
        if isinstance(nested, dict):
            usage = _merge_usage_max(usage, _usage_from_mapping(nested, depth + 1))

    if usage["total_tokens"] == 0 and (usage["prompt_tokens"] > 0 or usage["completion_tokens"] > 0):
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    return usage


def _to_usage_dict(raw: Any) -> Dict[str, int]:
    """
    Normalize heterogeneous usage shapes to:
    prompt_tokens / completion_tokens / total_tokens.
    """
    if raw is None:
        return empty_usage()

    if not isinstance(raw, dict):
        direct: Dict[str, Any] = {}
        for attr in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "request_tokens",
            "response_tokens",
            "input_tokens",
            "output_tokens",
            "prompt_token_count",
            "candidates_token_count",
            "total_token_count",
        ):
            if hasattr(raw, attr):
                direct[attr] = getattr(raw, attr)

        usage = _usage_from_mapping(direct) if direct else empty_usage()
        if usage["total_tokens"] > 0 or usage["prompt_tokens"] > 0 or usage["completion_tokens"] > 0:
            return usage
        if hasattr(raw, "__dict__"):
            raw = raw.__dict__
        else:
            return empty_usage()

    if not isinstance(raw, dict):
        return empty_usage()

    return _usage_from_mapping(raw)


def extract_usage(result: Any) -> Dict[str, int]:
    """Extract token usage robustly from heterogeneous response objects."""
    if result is None:
        return empty_usage()

    candidates: list[Any] = []
    candidates.append(result)

    if hasattr(result, "usage"):
        usage_attr = getattr(result, "usage")
        try:
            candidates.append(usage_attr() if callable(usage_attr) else usage_attr)
        except Exception:
            pass

    for attr in ("usage_metadata", "response_metadata", "model_extra", "_raw_response"):
        if hasattr(result, attr):
            try:
                candidates.append(getattr(result, attr))
            except Exception:
                pass

    messages_usage_sum = empty_usage()
    if isinstance(result, dict):
        for key in ("usage", "usage_metadata", "response_metadata", "token_usage"):
            if key in result:
                candidates.append(result.get(key))
        messages = result.get("messages")
        if isinstance(messages, list) and messages:
            for message in messages:
                direct_msg: Dict[str, Any] = {}
                for attr in (
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "request_tokens",
                    "response_tokens",
                    "input_tokens",
                    "output_tokens",
                    "prompt_token_count",
                    "candidates_token_count",
                    "total_token_count",
                ):
                    if hasattr(message, attr):
                        direct_msg[attr] = getattr(message, attr)
                if direct_msg:
                    messages_usage_sum = merge_usage(messages_usage_sum, _usage_from_mapping(direct_msg))
                if hasattr(message, "usage_metadata"):
                    messages_usage_sum = merge_usage(
                        messages_usage_sum,
                        _to_usage_dict(getattr(message, "usage_metadata")),
                    )
                if hasattr(message, "response_metadata"):
                    messages_usage_sum = merge_usage(
                        messages_usage_sum,
                        _to_usage_dict(getattr(message, "response_metadata")),
                    )

    final = empty_usage()
    for candidate in candidates:
        usage_piece = _to_usage_dict(candidate)
        final = _merge_usage_max(final, usage_piece)
    final = _merge_usage_max(final, messages_usage_sum)
    if final["total_tokens"] == 0 and (final["prompt_tokens"] > 0 or final["completion_tokens"] > 0):
        final["total_tokens"] = final["prompt_tokens"] + final["completion_tokens"]
    return final


def _compact(value: Any, limit: int = 100) -> str:
    text = str(value).replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _format_fields(fields: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in fields.items():
        if value is None or value == "":
            continue
        parts.append(f"{key}={_compact(value)}")
    return f" {' '.join(parts)}" if parts else ""


def log_console(scope: str, phase: str, name: str, **fields: Any) -> None:
    """Print one observability line when local observability is enabled."""
    if not _OBSERVABILITY_ENABLED:
        return
    print(f"   ↳ [{scope}:{phase}] {name}{_format_fields(fields)}", flush=True)


def log_agent_start(display_name: str, instruction: str | None = None) -> None:
    fields: dict[str, Any] = {}
    if instruction:
        fields["chars"] = len(instruction)
    log_console("agent", "start", display_name, **fields)


def log_agent_end(
    display_name: str,
    elapsed_s: float,
    status: str | None = None,
    reason: str | None = None,
    **extra_fields: Any,
) -> None:
    fields: dict[str, Any] = {
        "elapsed": f"{elapsed_s:.2f}s",
        "status": status,
        **extra_fields,
    }
    if status == "ERR" and reason:
        fields["reason"] = reason
    log_console("agent", "end", display_name, **fields)


def log_retry_start(agent_id: str, attempt: int, total_attempts: int) -> None:
    log_console("retry", "start", agent_id, attempt=f"{attempt}/{total_attempts}")


def log_retry_end(
    agent_id: str,
    attempt: int,
    elapsed_s: float,
    status: str | None = None,
    reason: str | None = None,
) -> None:
    fields: dict[str, Any] = {
        "attempt": attempt,
        "elapsed": f"{elapsed_s:.2f}s",
        "status": status,
    }
    if status == "ERR" and reason:
        fields["reason"] = reason
    log_console("retry", "end", agent_id, **fields)


def run_logged_tool(name: str, fn: Callable[[], Dict[str, Any]], **fields: Any) -> Dict[str, Any]:
    """Run a tool and emit compact start/end/error traces."""
    if not _OBSERVABILITY_ENABLED:
        return fn()
    log_console("tool", "start", name, **fields)
    started = perf_counter()
    try:
        result = fn()
    except Exception as exc:
        log_console(
            "tool",
            "err",
            name,
            elapsed=f"{perf_counter() - started:.2f}s",
            error=type(exc).__name__,
            detail=str(exc),
        )
        raise

    tool_status = result.get("status") if isinstance(result, dict) else None
    code = result.get("code") if isinstance(result, dict) else None
    log_console(
        "tool",
        "end",
        name,
        elapsed=f"{perf_counter() - started:.2f}s",
        status=tool_status,
        code=code,
    )
    return result


def log_turn_summary(elapsed_s: float, usage: Dict[str, int], turns_events: int | None = None) -> None:
    """Print per-turn telemetry summary (only with -obs)."""
    extra: Dict[str, Any] = {
        "elapsed": f"{elapsed_s:.2f}s",
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }
    if turns_events is not None:
        extra["events"] = turns_events
    log_console("turn", "summary", "Totals", **extra)
