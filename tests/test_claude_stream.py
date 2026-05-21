"""Tests RED para core/executors/claude_stream.py — parseo del stream-json de Claude Code.

`claude -p --output-format stream-json --verbose` emite un objeto JSON por línea:
eventos `assistant` (con bloques tool_use), `user` (tool_result) y un `result` final
con el texto, total_cost_usd y usage. Extraemos: texto final (para el hand-off),
traza de tool-calls (observabilidad), usage normalizado y coste real.
"""
from __future__ import annotations

import json

from orchestra.core.executors import claude_stream as cs


def _line(obj) -> str:
    return json.dumps(obj)


SAMPLE = [
    _line({"type": "system", "subtype": "init", "model": "claude-sonnet-4-6"}),
    _line({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Creo los tests primero."},
        {"type": "tool_use", "name": "Write", "input": {"file_path": "tests/test_slug.py"}},
    ]}}),
    _line({"type": "user", "message": {"content": [
        {"type": "tool_result", "content": "ok"},
    ]}}),
    _line({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Bash", "input": {"command": "pytest -q"}},
    ]}}),
    _line({"type": "result", "subtype": "success",
           "result": "Implementado slugify, 10 tests verdes.",
           "total_cost_usd": 0.0123,
           "usage": {"input_tokens": 5000, "output_tokens": 1200}}),
]


def test_extrae_texto_final():
    parsed = cs.parse_stream(SAMPLE)
    assert parsed.result_text == "Implementado slugify, 10 tests verdes."


def test_extrae_traza_de_tool_calls():
    parsed = cs.parse_stream(SAMPLE)
    nombres = [t.tool for t in parsed.trace]
    assert nombres == ["Write", "Bash"]
    # el resumen del input acompaña a la herramienta
    assert "tests/test_slug.py" in parsed.trace[0].summary


def test_extrae_coste_real_y_usage_normalizado():
    parsed = cs.parse_stream(SAMPLE)
    assert parsed.cost_usd == 0.0123
    # usage normalizado a prompt_tokens/completion_tokens (estilo OpenAI)
    assert parsed.usage["prompt_tokens"] == 5000
    assert parsed.usage["completion_tokens"] == 1200


def test_ignora_lineas_malformadas():
    lines = ["no es json {", *SAMPLE, ""]
    parsed = cs.parse_stream(lines)
    assert parsed.result_text == "Implementado slugify, 10 tests verdes."


def test_sin_result_devuelve_none_text():
    lines = [SAMPLE[0], SAMPLE[1]]   # init + un assistant, sin result final
    parsed = cs.parse_stream(lines)
    assert parsed.result_text is None
    assert parsed.cost_usd is None
    assert [t.tool for t in parsed.trace] == ["Write"]


def test_looks_like_stream_json():
    assert cs.looks_like_stream_json(SAMPLE) is True
    assert cs.looks_like_stream_json(["texto plano de codex/aider", "más texto"]) is False
    assert cs.looks_like_stream_json([]) is False


def test_tool_calls_in_line_extrae_de_una_linea():
    line = _line({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "voy a escribir"},
        {"type": "tool_use", "name": "Write", "input": {"file_path": "src/x.py"}},
        {"type": "tool_use", "name": "Bash", "input": {"command": "pytest"}},
    ]}})
    calls = cs.tool_calls_in_line(line)
    assert [c.tool for c in calls] == ["Write", "Bash"]
    assert "src/x.py" in calls[0].summary


def test_tool_calls_in_line_vacio_si_no_aplica():
    assert cs.tool_calls_in_line(_line({"type": "result", "result": "x"})) == []
    assert cs.tool_calls_in_line("no es json {") == []
    assert cs.tool_calls_in_line("") == []
