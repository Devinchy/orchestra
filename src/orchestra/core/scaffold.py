"""`orchestra init` — prepara un repo target para que orchestra orqueste ciclos.

Crea la estructura mínima (progress/, context/, orchestra.toml, PHASE_PLAN.md) que
hoy montábamos a mano. Idempotente: no sobrescribe archivos existentes, solo crea
los que falten. Agnóstico de SO y de CLI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from orchestra.core.executors import test_runner

_ACTIVE_PHASE = """# Fase activa

**Estado:** ninguna — edítalo o deja que el planner la genere.

## Objetivo
{{Qué deja listo esta fase.}}

## Condición de salida
- [ ] {{criterio verificable}}
"""

_ACTIVE_TASK = """# Tarea activa

**Estado:** ninguna — invoca el planner para generar una.

## Siguiente paso
`orchestra run planner --slug <slug>`  (o `orchestra cycle --slug <slug>`)
"""

_PHASE_PLAN = """# PHASE_PLAN

> Roadmap por fases. Lo gestiona el planner; puedes editarlo a mano.

## Fase activa: {{slug-fase}}

**Estado:** en_progreso

### Objetivo
{{2-3 frases.}}

### Tareas planificadas
- [ ] T-1: {{título}}
"""

_ORCHESTRA_TOML = """# Config del repo que orchestra lee.

[tests]
# Comando con el que el tester re-ejecuta los tests. Si está vacío, orchestra
# autodetecta (pytest / npm test / go test).
command = "{test_command}"
"""


@dataclass(frozen=True)
class InitResult:
    created: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def init_repo(repo_root: str | Path, *, test_command: str | None = None) -> InitResult:
    """Prepara `repo_root` para orchestra. No sobrescribe lo que ya exista."""
    repo_root = Path(repo_root)
    created: list[str] = []
    skipped: list[str] = []

    def _mkdir(rel: str) -> None:
        d = repo_root / rel
        if d.is_dir():
            skipped.append(rel)
        else:
            d.mkdir(parents=True, exist_ok=True)
            created.append(rel)

    def _write(rel: str, content: str) -> None:
        path = repo_root / rel
        if path.exists():
            skipped.append(rel)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created.append(rel)

    _mkdir("progress")
    _write("context/active-phase.md", _ACTIVE_PHASE)
    _write("context/active-task.md", _ACTIVE_TASK)
    _write("PHASE_PLAN.md", _PHASE_PLAN)

    cmd = test_command or test_runner.detect_test_command(repo_root) or ""
    _write("orchestra.toml", _ORCHESTRA_TOML.format(test_command=cmd))

    _ensure_gitignore(repo_root, "progress/", created, skipped)

    return InitResult(created=created, skipped=skipped)


def _ensure_gitignore(repo_root: Path, entry: str, created: list[str], skipped: list[str]) -> None:
    gi = repo_root / ".gitignore"
    existing = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    if entry in existing:
        skipped.append(f".gitignore ({entry})")
        return
    with gi.open("a", encoding="utf-8") as fh:
        if existing and existing[-1].strip():
            fh.write("\n")
        fh.write(f"{entry}\n")
    created.append(f".gitignore (+{entry})")
