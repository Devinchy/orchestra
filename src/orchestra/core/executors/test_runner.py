"""Executor acotado para el tester: corre los tests del repo y captura su output.

No edita nada — solo ejecuta el comando de tests. Así el tester se basa en el
resultado REAL de los tests, no en lo que reportó el builder. Autodetecta el
comando según el repo, con override explícito. subprocess inyectable.
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from orchestra.core.executors.base import CmdResult
from orchestra.core.executors.cli import _default_run

RunCmd = Callable[..., CmdResult]


@dataclass(frozen=True)
class TestRun:
    __test__ = False          # no es una clase de test (evita la colección de pytest)
    command: str | None       # None si no se pudo determinar
    output: str
    success: bool | None      # None si no había comando que correr


def detect_test_command(repo_root: Path) -> str | None:
    """Adivina el comando de tests del repo. None si no hay marcadores."""
    repo_root = Path(repo_root)
    if (repo_root / "pyproject.toml").exists() or (repo_root / "setup.py").exists():
        return "pytest"
    if (repo_root / "package.json").exists():
        return "npm test"
    if (repo_root / "go.mod").exists():
        return "go test ./..."
    return None


def run_tests(
    repo_root: Path,
    *,
    command: str | None = None,
    run_cmd: RunCmd = _default_run,
) -> TestRun:
    """Ejecuta el comando de tests (override o autodetectado) en el repo."""
    repo_root = Path(repo_root)
    cmd = command or detect_test_command(repo_root)
    if cmd is None:
        return TestRun(command=None, output="", success=None)

    result = run_cmd(shlex.split(cmd), cwd=repo_root, stdin_text=None)
    return TestRun(command=cmd, output=result.stdout, success=result.returncode == 0)
