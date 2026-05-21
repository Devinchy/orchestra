"""Tests RED para core/routing.py — selección de modelo, gate PII y fallback.

Es el corazón de orchestra: dado un rol y (opcionalmente) overrides de CLI, decide
qué proveedor/modelo corre, aplica el gate PII (rebota a un provider con DPA si hace
falta) y conoce la cadena de fallback por caída de proveedor.
"""
from __future__ import annotations

import pytest

from orchestra.core import routing
from orchestra.core.config import (
    OrchestraConfig,
    PiiGateConfig,
    ProviderSpec,
    RoleSpec,
    RoutingConfig,
)


def _make_config(*, pii_mode: str = "strict") -> OrchestraConfig:
    providers = {
        "claude": ProviderSpec(
            name="claude",
            proxy_models=["claude-opus-4-7", "claude-sonnet-4-6"],
            default_model="claude-sonnet-4-6",
            supports_mcp=True,
            supports_tools=True,
            dpa_signed=True,
        ),
        "codex": ProviderSpec(
            name="codex",
            proxy_models=["gpt-5-codex"],
            default_model="gpt-5-codex",
            supports_mcp=True,
            supports_tools=True,
            dpa_signed=False,
        ),
        "qwen": ProviderSpec(
            name="qwen",
            proxy_models=["qwen3-coder"],
            default_model="qwen3-coder",
            supports_mcp=False,
            supports_tools="limited",
            dpa_signed="self_hosted",
        ),
    }
    roles = {
        "builder": RoleSpec(
            name="builder",
            prompt="x.md",
            default_provider="claude",
            default_model="claude-sonnet-4-6",
            tools=["read", "edit"],
        ),
    }
    routing_cfg = RoutingConfig(
        pii_gate=PiiGateConfig(
            mode=pii_mode,
            sensitive_patterns_file="",
            strict_fallback_provider="claude",
            strict_fallback_model="claude-sonnet-4-6",
        ),
        fallback={"codex": "claude", "gemini": "claude"},
    )
    return OrchestraConfig(providers=providers, roles=roles, routing=routing_cfg)


# ---------- resolve_role_model ----------

def test_resolve_sin_overrides_usa_default_del_rol():
    c = _make_config()
    assert routing.resolve_role_model(c, "builder") == ("claude", "claude-sonnet-4-6")


def test_resolve_override_de_provider_usa_su_default_model():
    c = _make_config()
    assert routing.resolve_role_model(c, "builder", provider_override="codex") == (
        "codex",
        "gpt-5-codex",
    )


def test_resolve_override_provider_y_model():
    c = _make_config()
    got = routing.resolve_role_model(
        c, "builder", provider_override="claude", model_override="claude-opus-4-7"
    )
    assert got == ("claude", "claude-opus-4-7")


def test_resolve_solo_model_override_mantiene_provider_del_rol():
    c = _make_config()
    got = routing.resolve_role_model(c, "builder", model_override="claude-opus-4-7")
    assert got == ("claude", "claude-opus-4-7")


def test_resolve_rol_inexistente_falla():
    c = _make_config()
    with pytest.raises(routing.RoutingError, match="tester"):
        routing.resolve_role_model(c, "tester")


def test_resolve_modelo_fuera_de_proxy_models_falla():
    c = _make_config()
    with pytest.raises(routing.RoutingError, match="inventado"):
        routing.resolve_role_model(c, "builder", model_override="inventado")


# ---------- apply_pii_gate ----------

def test_gate_sin_pii_pasa_sin_cambios():
    c = _make_config()
    d = routing.apply_pii_gate(c, "codex", "gpt-5-codex", touches_pii=False)
    assert d.provider == "codex"
    assert d.action == "pass"


def test_gate_pii_con_provider_con_dpa_pasa():
    c = _make_config()
    d = routing.apply_pii_gate(c, "claude", "claude-sonnet-4-6", touches_pii=True)
    assert d.action == "pass"


def test_gate_pii_con_self_hosted_pasa():
    c = _make_config()
    d = routing.apply_pii_gate(c, "qwen", "qwen3-coder", touches_pii=True)
    assert d.action == "pass"


def test_gate_pii_sin_dpa_strict_rebota_a_fallback():
    c = _make_config(pii_mode="strict")
    d = routing.apply_pii_gate(c, "codex", "gpt-5-codex", touches_pii=True)
    assert d.action == "rerouted"
    assert d.provider == "claude"
    assert d.model == "claude-sonnet-4-6"


def test_gate_pii_sin_dpa_advisory_avisa_pero_mantiene():
    c = _make_config(pii_mode="advisory")
    d = routing.apply_pii_gate(c, "codex", "gpt-5-codex", touches_pii=True)
    assert d.action == "warned"
    assert d.provider == "codex"          # no rebota
    assert d.model == "gpt-5-codex"


# ---------- next_fallback ----------

def test_next_fallback_codex_es_claude():
    c = _make_config()
    assert routing.next_fallback(c, "codex") == "claude"


def test_next_fallback_provider_sin_entrada_es_none():
    c = _make_config()
    assert routing.next_fallback(c, "qwen") is None
