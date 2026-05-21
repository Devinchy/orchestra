"""Tests para core/runner.py — el pegamento end-to-end de un rol.

Encadena routing → pii gate → prompt → executor → transcript. Inyectamos un
FakeExecutor (sin red ni subprocess) para verificar la lógica; la selección real
de executor se prueba aparte con _select_executor.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from orchestra.core import config as cfg
from orchestra.core import runner
from orchestra.core.executors.base import ExecutionResult
from orchestra.core.executors.cli import CliExecutor
from orchestra.core.executors.proxy import ProxyExecutor
from orchestra.core.executors.test_runner import TestRun

ORCHESTRA_ROOT = Path(__file__).resolve().parents[1]
REPO_CONFIG = ORCHESTRA_ROOT / "config"


def _config():
    return cfg.load_config(REPO_CONFIG)


def _make_repo(tmp_path: Path, *, task_body: str, slug: str = "demo") -> Path:
    (tmp_path / "progress").mkdir()
    (tmp_path / "context").mkdir()
    (tmp_path / "progress" / f"task_{slug}.md").write_text(task_body, encoding="utf-8")
    return tmp_path


class FakeExecutor:
    """Registra con qué se le llamó y devuelve un content fijo."""
    def __init__(self, record: dict, *, content="OUTPUT DEL MODELO", files=None):
        self.record = record
        self.content = content
        self.files = files or []

    def execute(self, prompt, *, model, repo_root, role, slug):
        self.record["model"] = model
        self.record["prompt"] = prompt
        self.record["role"] = role
        return ExecutionResult(content=self.content, files_changed=self.files, success=True)


# ---------- run_role end-to-end (executor inyectado) ----------

def test_run_role_feliz_escribe_transcript_y_devuelve_resultado(tmp_path):
    repo = _make_repo(tmp_path, task_body="# Tarea\n\nToca `src/utils/math.py`. CA-1: sumar.")
    rec: dict = {}
    res = runner.run_role(
        _config(), "builder", "demo",
        repo_root=repo, orchestra_root=ORCHESTRA_ROOT,
        proxy_url="http://localhost:4000", api_key="sk-local",
        executor=FakeExecutor(rec, files=["src/utils/math.py"]),
    )
    assert res.provider == "claude"
    assert res.model == "claude-sonnet-4-6"
    assert res.gate_action == "pass"
    assert res.content == "OUTPUT DEL MODELO"
    assert res.files_changed == ["src/utils/math.py"]
    assert res.transcript_path.exists()
    assert "Rol: builder" in rec["prompt"]


def test_run_role_override_de_provider(tmp_path):
    repo = _make_repo(tmp_path, task_body="# Tarea\n\n`src/utils/math.py`. CA-1.")
    rec: dict = {}
    res = runner.run_role(
        _config(), "builder", "demo",
        repo_root=repo, orchestra_root=ORCHESTRA_ROOT,
        proxy_url="http://x", api_key="k",
        provider_override="codex",
        executor=FakeExecutor(rec),
    )
    assert res.provider == "codex"
    assert res.model == "gpt-5-codex"
    assert rec["model"] == "gpt-5-codex"


def test_run_role_pii_strict_rebota_a_claude(tmp_path):
    repo = _make_repo(tmp_path, task_body="# Tarea\n\nImplementar `src/auth/login.py`.")
    rec: dict = {}
    res = runner.run_role(
        _config(), "builder", "demo",
        repo_root=repo, orchestra_root=ORCHESTRA_ROOT,
        proxy_url="http://x", api_key="k",
        provider_override="codex",
        executor=FakeExecutor(rec),
    )
    assert res.gate_action == "rerouted"
    assert res.provider == "claude"
    assert rec["model"] == "claude-sonnet-4-6"


def test_run_role_task_inexistente_falla(tmp_path):
    (tmp_path / "progress").mkdir()
    with pytest.raises(Exception):
        runner.run_role(
            _config(), "builder", "noexiste",
            repo_root=tmp_path, orchestra_root=ORCHESTRA_ROOT,
            proxy_url="http://x", api_key="k",
            executor=FakeExecutor({}),
        )


# ---------- tester re-ejecuta tests y los mete en el prompt ----------

def test_tester_inyecta_output_de_tests_en_el_prompt(tmp_path):
    repo = _make_repo(tmp_path, task_body="# Tarea\n\n`src/x.py`. CA-1.")
    rec: dict = {}

    def fake_run_tests(repo_root):
        return TestRun(command="pytest", output="2 passed, 1 failed", success=False)

    runner.run_role(
        _config(), "tester", "demo",
        repo_root=repo, orchestra_root=ORCHESTRA_ROOT,
        proxy_url="http://x", api_key="k",
        executor=FakeExecutor(rec),
        run_tests_fn=fake_run_tests,
    )
    assert "TESTS RE-EJECUTADOS" in rec["prompt"]
    assert "2 passed, 1 failed" in rec["prompt"]


# ---------- selección de executor ----------

def test_select_executor_builder_codex_es_cli():
    ex = runner._select_executor(
        _config(), "builder", "codex",
        proxy_url="http://x", api_key="k", invoke_fn=lambda *a, **k: None,
    )
    assert isinstance(ex, CliExecutor)
    assert "codex" in ex.command_template


def test_select_executor_planner_es_proxy():
    ex = runner._select_executor(
        _config(), "planner", "claude",
        proxy_url="http://x", api_key="k", invoke_fn=lambda *a, **k: None,
    )
    assert isinstance(ex, ProxyExecutor)


def test_select_executor_builder_deepseek_es_cli_via_proxy():
    # deepseek -> aider (via_proxy): CliExecutor con env apuntando al proxy.
    ex = runner._select_executor(
        _config(), "builder", "deepseek",
        proxy_url="http://localhost:4000", api_key="sk-local",
        invoke_fn=lambda *a, **k: None,
    )
    assert isinstance(ex, CliExecutor)
    assert "aider" in ex.command_template
    assert ex.env["OPENAI_API_BASE"] == "http://localhost:4000"
    assert ex.env["OPENAI_API_KEY"] == "sk-local"


def test_select_executor_builder_sin_backend_cae_a_proxy():
    # Config con builder_backend vacío → el builder cae a ejecución documental.
    from orchestra.core.config import ExecutorConfig, OrchestraConfig
    base = _config()
    cfg_sin_backend = OrchestraConfig(
        providers=base.providers, roles=base.roles, routing=base.routing,
        executors=ExecutorConfig(),  # vacío
    )
    ex = runner._select_executor(
        cfg_sin_backend, "builder", "codex",
        proxy_url="http://x", api_key="k", invoke_fn=lambda *a, **k: None,
    )
    assert isinstance(ex, ProxyExecutor)
