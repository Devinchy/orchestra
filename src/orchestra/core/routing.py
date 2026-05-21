"""Enrutado: selección de modelo por rol, gate PII y cadena de fallback.

Núcleo de orchestra. Tres responsabilidades, todas funciones puras sobre la config
(testeables sin proxy ni API keys):

  resolve_role_model  — qué provider/model corre un rol, aplicando overrides de CLI.
  apply_pii_gate      — si la tarea toca PII, ¿el provider elegido puede verla? Si no,
                        rebota (strict) o avisa (advisory).
  next_fallback       — a qué provider saltar si el primario cae (lo usa el invoker).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from orchestra.core.config import OrchestraConfig

GateAction = Literal["pass", "warned", "rerouted"]


class RoutingError(ValueError):
    """Petición de enrutado imposible (rol o modelo inexistente)."""


@dataclass(frozen=True)
class GateDecision:
    """Resultado del gate PII."""
    provider: str
    model: str
    action: GateAction
    reason: str


def resolve_role_model(
    config: OrchestraConfig,
    role_name: str,
    *,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> tuple[str, str]:
    """Resuelve (provider, model) para un rol, aplicando overrides de CLI.

    Precedencia: override de CLI > default del rol. Un override de provider sin
    model usa el default_model de ESE provider; un override de model sin provider
    mantiene el provider del rol.
    """
    role = config.roles.get(role_name)
    if role is None:
        raise RoutingError(
            f"rol '{role_name}' no existe — definidos: {sorted(config.roles)}"
        )

    provider_name = provider_override or role.default_provider
    provider = config.providers.get(provider_name)
    if provider is None:
        raise RoutingError(
            f"provider '{provider_name}' no existe — definidos: {sorted(config.providers)}"
        )

    if model_override is not None:
        model = model_override
    elif provider_override is not None:
        # Cambiaste de provider sin decir modelo → el default del nuevo provider.
        model = provider.default_model
    else:
        model = role.default_model

    if model not in provider.proxy_models:
        raise RoutingError(
            f"modelo '{model}' no está en proxy_models de '{provider_name}' "
            f"{provider.proxy_models}"
        )

    return provider_name, model


def apply_pii_gate(
    config: OrchestraConfig,
    provider_name: str,
    model: str,
    *,
    touches_pii: bool,
) -> GateDecision:
    """Aplica el gate PII a un (provider, model) ya resuelto.

    - Si la tarea no toca PII → pasa.
    - Si la toca y el provider puede verla legalmente (DPA o self_hosted) → pasa.
    - Si no puede:
        * mode "strict"   → rebota al strict_fallback (provider con DPA).
        * mode "advisory" → avisa pero mantiene el provider elegido.
    """
    provider = config.providers.get(provider_name)
    if provider is None:
        raise RoutingError(f"provider '{provider_name}' no existe")

    if not touches_pii:
        return GateDecision(provider_name, model, "pass", "la tarea no toca PII")

    if provider.can_process_pii:
        return GateDecision(
            provider_name, model, "pass",
            f"'{provider_name}' puede procesar PII (dpa_signed={provider.dpa_signed!r})",
        )

    gate = config.routing.pii_gate
    if gate.mode == "strict":
        return GateDecision(
            gate.strict_fallback_provider,
            gate.strict_fallback_model,
            "rerouted",
            f"PII + '{provider_name}' sin DPA + gate strict -> rebote a "
            f"'{gate.strict_fallback_provider}'",
        )

    # advisory
    return GateDecision(
        provider_name, model, "warned",
        f"[AVISO] PII + '{provider_name}' sin DPA (gate advisory) -- verifica que el "
        f"DPA con este proveedor esta vigente",
    )


def next_fallback(config: OrchestraConfig, provider_name: str) -> str | None:
    """Provider al que saltar si `provider_name` cae. None si no hay regla."""
    return config.routing.fallback.get(provider_name)
