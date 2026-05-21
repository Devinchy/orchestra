"""Invocación de un modelo a través del proxy litellm local.

orchestra NO importa litellm ni habla con los proveedores directamente: manda una
petición OpenAI-compatible al proxy (localhost:4000) por HTTP. El proxy enruta al
proveedor real y expone el MCP bridge (Engram). Así el mismo código sirve para
Claude, Codex, DeepSeek, Qwen o Gemini — solo cambia el `model`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

_DEFAULT_TIMEOUT = 600.0  # los builders/planners largos tardan minutos


class InvocationError(RuntimeError):
    """La llamada al proxy falló o devolvió algo inutilizable."""


@dataclass(frozen=True)
class InvocationResult:
    content: str
    model: str
    finish_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


def invoke(
    messages: list[dict[str, Any]],
    *,
    model: str,
    proxy_url: str,
    api_key: str,
    tools: list[dict[str, Any]] | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
    client: httpx.Client | None = None,
) -> InvocationResult:
    """Llama a /v1/chat/completions del proxy y devuelve el contenido del asistente.

    Args:
        messages: mensajes en formato OpenAI chat.
        model: nombre del modelo tal como lo conoce el proxy (model_list de litellm.yaml).
        proxy_url: base del proxy (p. ej. http://localhost:4000).
        api_key: master key del proxy (Bearer).
        tools: tool specs OpenAI, opcional.
        client: httpx.Client inyectable (para tests). Si None, se crea y se cierra.

    Raises:
        InvocationError: status != 2xx, respuesta sin choices, o error de red.
    """
    url = f"{proxy_url.rstrip('/')}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {"model": model, "messages": messages}
    if tools:
        payload["tools"] = tools

    owns_client = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        try:
            resp = client.post(url, json=payload, headers=headers, timeout=timeout)
        except httpx.HTTPError as e:
            raise InvocationError(f"error de red llamando al proxy ({url}): {e}") from e

        if resp.status_code // 100 != 2:
            raise InvocationError(
                f"el proxy devolvió status {resp.status_code}: {resp.text[:500]}"
            )

        try:
            data = resp.json()
        except ValueError as e:
            raise InvocationError(f"respuesta del proxy no es JSON: {resp.text[:200]}") from e

        choices = data.get("choices") or []
        if not choices:
            raise InvocationError(f"respuesta del proxy sin choices: {data}")

        message = choices[0].get("message", {})
        content = message.get("content")
        if content is None:
            raise InvocationError(f"choice sin content: {choices[0]}")

        return InvocationResult(
            content=content,
            model=data.get("model", model),
            finish_reason=choices[0].get("finish_reason"),
            usage=data.get("usage", {}),
            raw=data,
        )
    finally:
        if owns_client:
            client.close()
