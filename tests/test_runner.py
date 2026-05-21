"""Tests RED para core/runner.py — el pegamento end-to-end de un rol.

run_role encadena las piezas ya testeadas: resuelve modelo (routing) → detecta PII
en la tarea (pii) → aplica el gate (puede cambiar el modelo) → compone el prompt
(prompt_builder) → invoca el proxy (invoker, aquí inyectado/fake) → captura el
transcript. Sin red: pasamos un invoke_fn fake que registra con qué se le llamó.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from orchestra.core import config as cfg
from orchestra.core import runner
from orchestra.core.invoker import InvocationResult

ORCHESTRA_ROOT = Path(__file__).resolve().parents[1]
REPO_CONFIG = ORCHESTRA_ROOT / "config"


def _config():
    return cfg.load_config(REPO_CONFIG)


def _make_repo(tmp_path: Path, *, task_body: str, slug: str = "demo") -> Path:
    (tmp_path / "progress").mkdir()
    (tmp_path / "context").mkdir()
    (tmp_path / "progress" / f"task_{slug}.md").write_text(task_body, encoding="utf-8")
    return tmp_path


def _fake_invoke(record: dict):
    """Devuelve un invoke_fn que guarda sus kwargs y responde algo fijo."""
    def _inner(messages, *, model, proxy_url, api_key, tools=None, **kw):
        record["model"] = model
        record["proxy_url"] = proxy_url
        record["api_key"] = api_key
        record["prompt"] = messages[0]["content"]
        return InvocationResult(content="OUTPUT DEL MODELO", model=model,
                                finish_reason="stop")
    return _inner


def test_run_role_feliz_escribe_transcript_y_devuelve_resultado(tmp_path):
    repo = _make_repo(tmp_path, task_body="# Tarea\n\nToca `src/utils/math.py`. CA-1: sumar.")
    rec: dict = {}
    res = runner.run_role(
        _config(), "builder", "demo",
        repo_root=repo, orchestra_root=ORCHESTRA_ROOT,
        proxy_url="http://localhost:4000", api_key="sk-local",
        invoke_fn=_fake_invoke(rec),
    )
    # Sin PII y rol builder → su default (claude/sonnet).
    assert res.provider == "claude"
    assert res.model == "claude-sonnet-4-6"
    assert res.gate_action == "pass"
    assert res.content == "OUTPUT DEL MODELO"
    assert res.transcript_path.exists()
    assert "OUTPUT DEL MODELO" in res.transcript_path.read_text(encoding="utf-8")
    # El prompt que recibió el modelo lleva el contrato del rol.
    assert "Rol: builder" in rec["prompt"]


def test_run_role_override_de_provider(tmp_path):
    repo = _make_repo(tmp_path, task_body="# Tarea\n\n`src/utils/math.py`. CA-1.")
    rec: dict = {}
    res = runner.run_role(
        _config(), "builder", "demo",
        repo_root=repo, orchestra_root=ORCHESTRA_ROOT,
        proxy_url="http://x", api_key="k",
        provider_override="codex",
        invoke_fn=_fake_invoke(rec),
    )
    assert res.provider == "codex"
    assert res.model == "gpt-5-codex"
    assert rec["model"] == "gpt-5-codex"


def test_run_role_pii_strict_rebota_a_claude(tmp_path):
    # Tarea que toca PII (auth) + provider codex sin DPA + gate strict (config real).
    repo = _make_repo(tmp_path, task_body="# Tarea\n\nImplementar `src/auth/login.py`.")
    rec: dict = {}
    res = runner.run_role(
        _config(), "builder", "demo",
        repo_root=repo, orchestra_root=ORCHESTRA_ROOT,
        proxy_url="http://x", api_key="k",
        provider_override="codex",          # pedimos codex...
        invoke_fn=_fake_invoke(rec),
    )
    # ...pero el gate strict lo rebota a claude porque la tarea toca PII.
    assert res.gate_action == "rerouted"
    assert res.provider == "claude"
    assert rec["model"] == "claude-sonnet-4-6"   # el modelo que REALMENTE se invocó


def test_run_role_task_inexistente_falla(tmp_path):
    (tmp_path / "progress").mkdir()
    with pytest.raises(Exception):
        runner.run_role(
            _config(), "builder", "noexiste",
            repo_root=tmp_path, orchestra_root=ORCHESTRA_ROOT,
            proxy_url="http://x", api_key="k",
            invoke_fn=_fake_invoke({}),
        )
