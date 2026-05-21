"""Smoke tests para cli.py — la lógica de verdad vive en runner; aquí solo
verificamos que el CLI parsea args, pasa overrides y maneja errores con gracia.
"""
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from orchestra import cli
from orchestra.core.cycle import CycleResult
from orchestra.core.runner import RunResult


def _fake_result(provider="claude", model="claude-sonnet-4-6", action="pass"):
    return RunResult(
        role="builder", provider=provider, model=model,
        gate_action=action, gate_reason="ok", pii_paths=[],
        content="hecho", transcript_path=Path("progress/transcript_demo.md"),
    )


def test_help_lista_comandos():
    res = CliRunner().invoke(cli.main, ["--help"])
    assert res.exit_code == 0
    assert "run" in res.output
    assert "status" in res.output


def test_run_pasa_args_a_run_role(monkeypatch):
    captured = {}

    def fake_run_role(config, role, slug, **kw):
        captured["role"] = role
        captured["slug"] = slug
        captured["provider_override"] = kw.get("provider_override")
        captured["model_override"] = kw.get("model_override")
        return _fake_result()

    monkeypatch.setattr(cli.runner, "run_role", fake_run_role)

    res = CliRunner().invoke(
        cli.main, ["run", "builder", "--slug", "demo", "--provider", "codex"]
    )
    assert res.exit_code == 0, res.output
    assert captured["role"] == "builder"
    assert captured["slug"] == "demo"
    assert captured["provider_override"] == "codex"
    assert captured["model_override"] is None
    # El resumen menciona provider/model resueltos.
    assert "claude" in res.output


def test_run_muestra_rerouted_cuando_el_gate_rebota(monkeypatch):
    monkeypatch.setattr(
        cli.runner, "run_role",
        lambda *a, **k: _fake_result(provider="claude", action="rerouted"),
    )
    res = CliRunner().invoke(cli.main, ["run", "builder", "--slug", "demo",
                                        "--provider", "codex"])
    assert res.exit_code == 0
    assert "rerouted" in res.output.lower() or "rebot" in res.output.lower()


def test_run_error_se_muestra_limpio(monkeypatch):
    def boom(*a, **k):
        raise ValueError("algo falló")

    monkeypatch.setattr(cli.runner, "run_role", boom)
    res = CliRunner().invoke(cli.main, ["run", "builder", "--slug", "demo"])
    assert res.exit_code != 0
    assert "algo falló" in res.output


def test_status_sin_tarea_activa(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = CliRunner().invoke(cli.main, ["status"])
    assert res.exit_code == 0
    assert "ninguna" in res.output.lower()


# ---------- cycle ----------

def test_cycle_all_aplica_mismo_provider_a_los_tres(monkeypatch):
    captured = {}

    def fake_run_cycle(config, slug, **kw):
        captured["overrides"] = kw.get("provider_overrides")
        return CycleResult("PASS", None, 1, "pass", history=[])

    monkeypatch.setattr(cli.cycle_core, "run_cycle", fake_run_cycle)
    res = CliRunner().invoke(cli.main, ["cycle", "--slug", "demo", "--all", "codex"])
    assert res.exit_code == 0, res.output
    assert captured["overrides"] == {"planner": "codex", "builder": "codex", "tester": "codex"}


def test_cycle_overrides_por_rol(monkeypatch):
    captured = {}

    def fake_run_cycle(config, slug, **kw):
        captured["overrides"] = kw.get("provider_overrides")
        return CycleResult("PASS", None, 1, "pass", history=[])

    monkeypatch.setattr(cli.cycle_core, "run_cycle", fake_run_cycle)
    res = CliRunner().invoke(
        cli.main,
        ["cycle", "--slug", "demo", "--planner", "codex", "--builder", "claude"],
    )
    assert res.exit_code == 0, res.output
    assert captured["overrides"] == {"planner": "codex", "builder": "claude"}


def test_cycle_exit_1_si_no_pasa(monkeypatch):
    monkeypatch.setattr(
        cli.cycle_core, "run_cycle",
        lambda *a, **k: CycleResult("FAIL", "builder", 3, "max_iters", history=[]),
    )
    res = CliRunner().invoke(cli.main, ["cycle", "--slug", "demo"])
    assert res.exit_code == 1


# ---------- config show ----------

def test_config_show_lista_la_config_real():
    res = CliRunner().invoke(cli.main, ["config", "show"])
    assert res.exit_code == 0, res.output
    assert "PROVEEDORES" in res.output
    assert "claude" in res.output
    assert "GATE PII" in res.output
    assert "BUILDER por proveedor" in res.output
    # los backends del builder aparecen
    assert "aider" in res.output or "via proxy" in res.output
