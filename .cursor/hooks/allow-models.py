#!/usr/bin/env python3
"""Allow Composer 2.5 and Grok 4.7, and reject fast variants.

Cursor loads this hook from .cursor/hooks.json in a trusted checkout, including
the CLI and cloud agents. The IDE reports Grok 4.7 Medium as model grok-4.7
with no effort field. An empty subagent model means inherit and is allowed.
"""

from __future__ import annotations

import json
import sys

_DISPLAY_NAMES = {
    "composer 2.5": "composer-2.5",
    "grok 4.7": "grok-4.7",
    "grok 4.7 medium": "grok-4.7-medium",
}


def main() -> int:
    try:
        payload = load_payload()
    except Exception:
        payload = None
    if payload is None:
        _emit({"permission": "allow"})
        return 0
    reason = rejection_reason(payload)
    if reason:
        return _deny(reason, include_agent_message=payload.get("hook_event_name") != "subagentStart")
    _emit({"permission": "allow"})
    return 0


def load_payload() -> dict | None:
    raw = sys.stdin.buffer.read()
    if not raw.strip(b"\x00 \t\r\n"):
        return {}
    text = _decode(raw).strip().lstrip("\ufeff")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(value, dict):
        return None
    return value


def _decode(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")) or raw.startswith(b"{\x00"):
        return raw.decode("utf-16")
    if raw.startswith(b"\x00"):
        return raw.decode("utf-16-be")
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _emit(payload: dict) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.stdout.flush()


def rejection_reason(payload: dict) -> str:
    subagent = subagent_model(payload)
    if subagent and not is_allowed(subagent, _params(payload.get("model_params"))):
        return _message(subagent)
    return _parent_rejection(payload)


def _parent_rejection(payload: dict) -> str:
    """Allow the session when any reported field is Composer 2.5 or Grok 4.7."""
    params = _params(payload.get("model_params"))
    reported = [str(payload.get(key) or "").strip() for key in ("model", "model_id")]
    reported = [token for token in reported if token]
    if not reported:
        return ""
    if any(is_allowed(token, params) for token in reported):
        return ""
    detail = ", ".join(reported)
    if params:
        detail += f" params={params}"
    return _message(detail)


def _params(value: object) -> dict[str, str]:
    params: dict[str, str] = {}
    if not isinstance(value, list):
        return params
    for item in value:
        if not isinstance(item, dict):
            continue
        key = item.get("id") or item.get("name")
        if key:
            params[str(key)] = str(item.get("value") or "")
    return params


def subagent_model(payload: dict) -> str:
    direct = str(payload.get("subagent_model") or "").strip()
    if direct:
        return direct
    event = str(payload.get("hook_event_name") or "")
    tool_name = str(payload.get("tool_name") or "")
    if event != "preToolUse" or tool_name != "Task":
        return ""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    for key in ("model", "model_id", "subagent_model"):
        value = str(tool_input.get(key) or "").strip()
        if value:
            return value
    return ""


def is_allowed(token: str, extra_params: dict[str, str]) -> bool:
    base, params = _split_model(token)
    for key, value in extra_params.items():
        params.setdefault(key, value.lower())
    if params.get("fast") in {"true", "1", "yes"}:
        return False
    if base == "composer-2.5" or base == "grok-4.7":
        return True
    effort = base.removeprefix("grok-4.7-")
    return base.startswith("grok-4.7-") and effort in {"low", "medium", "high", "xhigh", "max"}


def _split_model(token: str) -> tuple[str, dict[str, str]]:
    text = token.strip()
    mapped = _DISPLAY_NAMES.get(text.casefold())
    if mapped:
        text = mapped
    params: dict[str, str] = {}
    if "[" in text and text.endswith("]"):
        base, rest = text[:-1].split("[", 1)
        text = base.strip()
        for part in rest.split(","):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            params[key.strip()] = value.strip().lower()
    if text.endswith("-fast"):
        params["fast"] = "true"
        text = text[: -len("-fast")]
    return text, params


def _message(model: str) -> str:
    return (
        "このリポジトリで使えるモデルは composer-2.5 と grok-4.7 です。fast は使えません。"
        f"要求されたモデルは {model} でした。"
        "サブエージェントは model を省略して親を継承してください。"
    )


def _deny(message: str, *, include_agent_message: bool = True) -> int:
    payload = {"permission": "deny", "user_message": message}
    if include_agent_message:
        payload["agent_message"] = message
    _emit(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
