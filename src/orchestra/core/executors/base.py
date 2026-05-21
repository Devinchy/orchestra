"""Abstracción de ejecución de un rol.

Dos implementaciones (proxy.py, cli.py). El runner elige según el rol:
  - planner/tester → ProxyExecutor (razonar, devolver texto).
  - builder        → CliExecutor (delegar a un CLI agéntico que edita el repo).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class CmdResult:
    """Resultado de ejecutar un comando externo."""
    returncode: int
    stdout: str


@dataclass(frozen=True)
class ExecutionResult:
    content: str
    files_changed: list[str] = field(default_factory=list)
    tests_output: str | None = None
    success: bool = True
    usage: dict = field(default_factory=dict)   # tokens (proxy); vacío en CLI


class Executor(Protocol):
    """Ejecuta un rol sobre una tarea y devuelve su resultado."""

    def execute(
        self,
        prompt: str,
        *,
        model: str,
        repo_root: Path,
        role: str,
        slug: str,
    ) -> ExecutionResult:
        ...
