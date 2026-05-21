"""Tests RED para core/invoker.py — llamada al proxy litellm (OpenAI-compatible).

No tocamos la red real: httpx.MockTransport simula el proxy. Verificamos que el
payload sale bien formado, que parseamos la respuesta, y que un error HTTP se
convierte en InvocationError (no en un crash opaco).
"""
from __future__ import annotations

import json

import httpx
import pytest

from orchestra.core import invoker


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "gpt-5-codex",
            "choices": [
                {"message": {"role": "assistant", "content": "hecho"},
                 "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3},
        },
    )


def test_invoke_devuelve_contenido_y_modelo():
    res = invoker.invoke(
        [{"role": "user", "content": "hola"}],
        model="gpt-5-codex",
        proxy_url="http://localhost:4000",
        api_key="sk-local",
        client=_client(_ok_response),
    )
    assert res.content == "hecho"
    assert res.model == "gpt-5-codex"
    assert res.finish_reason == "stop"
    assert res.usage["completion_tokens"] == 3


def test_invoke_construye_payload_correcto():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return _ok_response(request)

    invoker.invoke(
        [{"role": "user", "content": "hola"}],
        model="claude-sonnet-4-6",
        proxy_url="http://localhost:4000/",   # con barra final a propósito
        api_key="sk-local",
        tools=[{"type": "function", "function": {"name": "read"}}],
        client=_client(handler),
    )
    assert captured["url"] == "http://localhost:4000/v1/chat/completions"
    assert captured["auth"] == "Bearer sk-local"
    assert captured["body"]["model"] == "claude-sonnet-4-6"
    assert captured["body"]["messages"][0]["content"] == "hola"
    assert captured["body"]["tools"][0]["function"]["name"] == "read"


def test_invoke_sin_tools_no_incluye_la_clave():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _ok_response(request)

    invoker.invoke(
        [{"role": "user", "content": "x"}],
        model="gpt-5",
        proxy_url="http://localhost:4000",
        api_key="sk-local",
        client=_client(handler),
    )
    assert "tools" not in captured["body"]


def test_invoke_status_error_lanza_invocation_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    with pytest.raises(invoker.InvocationError, match="500"):
        invoker.invoke(
            [{"role": "user", "content": "x"}],
            model="gpt-5",
            proxy_url="http://localhost:4000",
            api_key="sk-local",
            client=_client(handler),
        )


def test_invoke_respuesta_sin_choices_lanza_invocation_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "x", "choices": []})

    with pytest.raises(invoker.InvocationError, match="choices"):
        invoker.invoke(
            [{"role": "user", "content": "x"}],
            model="gpt-5",
            proxy_url="http://localhost:4000",
            api_key="sk-local",
            client=_client(handler),
        )
