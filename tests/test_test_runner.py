"""Tests RED para core/executors/test_runner.py — el executor acotado del tester.

El tester re-ejecuta los tests de verdad (no se fía del builder), pero NO edita
nada: solo corre el comando de tests y captura su output. Autodetecta el comando
según el repo, con override. subprocess inyectado para tests.
"""
from __future__ import annotations

from orchestra.core.executors import test_runner as tr
from orchestra.core.executors.base import CmdResult


def test_detecta_pytest_si_hay_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'", encoding="utf-8")
    assert tr.detect_test_command(tmp_path) == "pytest"


def test_detecta_npm_si_hay_package_json(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    assert tr.detect_test_command(tmp_path) == "npm test"


def test_sin_marcadores_devuelve_none(tmp_path):
    assert tr.detect_test_command(tmp_path) is None


def test_run_tests_usa_override_sobre_autodeteccion(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]", encoding="utf-8")
    calls = {}

    def fake_run(argv, *, cwd, stdin_text):
        calls["argv"] = argv
        return CmdResult(returncode=0, stdout="5 passed")

    run = tr.run_tests(tmp_path, command="pytest -k upload", run_cmd=fake_run)
    assert run.command == "pytest -k upload"
    assert calls["argv"] == ["pytest", "-k", "upload"]
    assert run.success is True
    assert "5 passed" in run.output


def test_run_tests_autodetecta_si_no_hay_override(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]", encoding="utf-8")

    def fake_run(argv, *, cwd, stdin_text):
        return CmdResult(returncode=1, stdout="1 failed")

    run = tr.run_tests(tmp_path, run_cmd=fake_run)
    assert run.command == "pytest"
    assert run.success is False
    assert "1 failed" in run.output


def test_run_tests_sin_comando_detectable(tmp_path):
    run = tr.run_tests(tmp_path, run_cmd=lambda *a, **k: CmdResult(0, ""))
    assert run.command is None
    assert run.success is None      # no se pudo determinar
