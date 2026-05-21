"""Tests RED para core/config.py — carga y validación de la config TOML.

config.py lee config/{providers,roles,routing}.toml con tomllib (stdlib) y los
convierte en dataclasses validadas. La validación debe fallar RÁPIDO y CLARO ante
config incoherente (rol que apunta a un provider inexistente, fallback PII a un
provider sin DPA, etc.) — un typo no debe descubrirse a mitad de un ciclo.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from orchestra.core import config as cfg

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config"


# ---------- Caso feliz: la config real del repo carga ----------

def test_carga_config_real_del_repo():
    c = cfg.load_config(REPO_CONFIG)
    assert "claude" in c.providers
    assert "builder" in c.roles
    assert c.routing.pii_gate.mode in {"advisory", "strict"}


def test_provider_claude_tiene_dpa():
    c = cfg.load_config(REPO_CONFIG)
    assert c.providers["claude"].dpa_signed is True


def test_qwen_es_self_hosted():
    c = cfg.load_config(REPO_CONFIG)
    assert c.providers["qwen"].dpa_signed == "self_hosted"


def test_rol_builder_default_es_sonnet():
    c = cfg.load_config(REPO_CONFIG)
    builder = c.roles["builder"]
    assert builder.default_provider == "claude"
    assert builder.default_model == "claude-sonnet-4-6"


# ---------- Validaciones: config incoherente debe reventar ----------

def _write_min_config(tmp: Path, *, providers: str, roles: str, routing: str) -> Path:
    (tmp / "providers.toml").write_text(providers, encoding="utf-8")
    (tmp / "roles.toml").write_text(roles, encoding="utf-8")
    (tmp / "routing.toml").write_text(routing, encoding="utf-8")
    return tmp


_GOOD_PROVIDERS = """
[providers.claude]
proxy_models = ["claude-sonnet-4-6"]
default_model = "claude-sonnet-4-6"
supports_mcp = true
supports_tools = true
dpa_signed = true
"""

_GOOD_ROUTING = """
[pii_gate]
mode = "strict"
sensitive_patterns_file = ""
[pii_gate.strict_fallback]
provider = "claude"
model = "claude-sonnet-4-6"
[fallback]
"""


def test_rol_apunta_a_provider_inexistente_falla(tmp_path):
    roles = """
[roles.builder]
prompt = "x.md"
default_provider = "nope"
default_model = "claude-sonnet-4-6"
tools = ["read"]
"""
    _write_min_config(tmp_path, providers=_GOOD_PROVIDERS, roles=roles, routing=_GOOD_ROUTING)
    with pytest.raises(cfg.ConfigError, match="nope"):
        cfg.load_config(tmp_path)


def test_rol_con_modelo_fuera_de_proxy_models_falla(tmp_path):
    roles = """
[roles.builder]
prompt = "x.md"
default_provider = "claude"
default_model = "modelo-inventado"
tools = ["read"]
"""
    _write_min_config(tmp_path, providers=_GOOD_PROVIDERS, roles=roles, routing=_GOOD_ROUTING)
    with pytest.raises(cfg.ConfigError, match="modelo-inventado"):
        cfg.load_config(tmp_path)


def test_pii_gate_mode_invalido_falla(tmp_path):
    routing = _GOOD_ROUTING.replace('mode = "strict"', 'mode = "paranoid"')
    roles = """
[roles.builder]
prompt = "x.md"
default_provider = "claude"
default_model = "claude-sonnet-4-6"
tools = ["read"]
"""
    _write_min_config(tmp_path, providers=_GOOD_PROVIDERS, roles=roles, routing=routing)
    with pytest.raises(cfg.ConfigError, match="paranoid"):
        cfg.load_config(tmp_path)


def test_fallback_pii_a_provider_sin_dpa_falla(tmp_path):
    # El strict_fallback DEBE apuntar a un provider con DPA o self_hosted.
    providers = _GOOD_PROVIDERS + """
[providers.codex]
proxy_models = ["gpt-5-codex"]
default_model = "gpt-5-codex"
supports_mcp = true
supports_tools = true
dpa_signed = false
"""
    routing = _GOOD_ROUTING.replace('provider = "claude"', 'provider = "codex"')
    roles = """
[roles.builder]
prompt = "x.md"
default_provider = "claude"
default_model = "claude-sonnet-4-6"
tools = ["read"]
"""
    _write_min_config(tmp_path, providers=providers, roles=roles, routing=routing)
    with pytest.raises(cfg.ConfigError, match="DPA"):
        cfg.load_config(tmp_path)
