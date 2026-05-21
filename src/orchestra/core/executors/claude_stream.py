"""Parseo del stream-json de Claude Code (`claude -p --output-format stream-json`).

Cada línea es un objeto JSON. Nos interesan:
  - `assistant` con bloques `tool_use` → traza de qué herramientas usó el builder.
  - `result` final → texto de salida, total_cost_usd, usage real.

Devuelve un ParsedStream con: texto final (para el hand-off), traza (observabilidad),
usage normalizado a estilo OpenAI (prompt/completion_tokens) y coste real reportado
por Claude. Para otros CLIs (codex/aider) que emiten texto plano, ver looks_like_stream_json.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolCall:
    tool: str
    summary: str   # resumen corto del input (primer valor relevante)


@dataclass(frozen=True)
class ParsedStream:
    result_text: str | None
    trace: list[ToolCall] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    cost_usd: float | None = None


def _summarize_input(tool_input: dict) -> str:
    """Resumen corto del input de una tool (path, comando, patrón…)."""
    if not isinstance(tool_input, dict):
        return ""
    for key in ("file_path", "path", "command", "pattern", "url", "query"):
        if key in tool_input:
            return str(tool_input[key])[:120]
    # primer valor escalar disponible
    for v in tool_input.values():
        if isinstance(v, (str, int, float)):
            return str(v)[:120]
    return ""


def tool_calls_in_line(line: str) -> list[ToolCall]:
    """Extrae los tool_use de UNA línea JSONL (para parseo incremental en streaming).

    Vacío si la línea no parsea, no es un evento `assistant`, o no tiene tool_use.
    """
    s = line.strip()
    if not s:
        return []
    try:
        obj = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(obj, dict) or obj.get("type") != "assistant":
        return []
    calls: list[ToolCall] = []
    for block in (obj.get("message") or {}).get("content") or []:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            calls.append(ToolCall(
                tool=block.get("name", "?"),
                summary=_summarize_input(block.get("input", {})),
            ))
    return calls


def looks_like_stream_json(lines: list[str]) -> bool:
    """True si la salida parece JSONL de Claude Code (1ª línea no vacía es un objeto con 'type')."""
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except (json.JSONDecodeError, ValueError):
            return False
        return isinstance(obj, dict) and "type" in obj
    return False


def parse_stream(lines: list[str]) -> ParsedStream:
    """Extrae texto final, traza de tool-calls, usage y coste del JSONL."""
    trace: list[ToolCall] = []
    result_text: str | None = None
    usage: dict = {}
    cost_usd: float | None = None

    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(obj, dict):
            continue

        kind = obj.get("type")
        if kind == "assistant":
            trace.extend(tool_calls_in_line(raw))
        elif kind == "result":
            result_text = obj.get("result")
            cost_usd = obj.get("total_cost_usd")
            u = obj.get("usage") or {}
            usage = {
                "prompt_tokens": u.get("input_tokens", 0),
                "completion_tokens": u.get("output_tokens", 0),
            }

    return ParsedStream(result_text=result_text, trace=trace, usage=usage, cost_usd=cost_usd)
