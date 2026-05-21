"""Composición del prompt que se envía al modelo, por rol.

Generaliza el build-builder-prompt.sh de dev-config a cualquiera de los 3 roles.
Concatena:
  - el contrato del rol (roles/<rol>.md)
  - las rules de implementación aplicables
  - artefactos del repo target que existan (CLAUDE.md, context, task, tests, etc.)

Dos roots distintos:
  - orchestra_root : dónde viven roles/ y rules/ (la instalación de orchestra).
  - repo_root      : el proyecto donde corre el ciclo (progress/, context/, CLAUDE.md).
"""
from __future__ import annotations

import re
from pathlib import Path

from orchestra.core.config import OrchestraConfig

# Rules de implementación inyectadas siempre (si existen en orchestra_root).
_ALWAYS_RULES = ["00-general", "10-security", "20-testing", "60-git-pr", "70-data-rgpd"]

# Rules condicionales al stack del repo target: rule → marcadores que la activan.
_STACK_RULES = {
    "30-python-playwright": ("pyproject.toml", "requirements.txt"),
}

_FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


class PromptError(ValueError):
    """No se pudo componer el prompt (rol o artefacto obligatorio ausente)."""


def strip_frontmatter(text: str) -> str:
    """Quita el frontmatter YAML (--- ... ---) del inicio, si lo hay."""
    return _FRONTMATTER.sub("", text, count=1)


def _section(title: str, body: str) -> str:
    return f"\n\n=== {title} ===\n\n{body.strip()}\n"


def _read(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def build_prompt(
    config: OrchestraConfig,
    role_name: str,
    slug: str,
    *,
    repo_root: Path,
    orchestra_root: Path | None = None,
) -> str:
    """Compone el prompt para `role_name` sobre la tarea `slug`.

    Lanza PromptError si el rol no existe o si falta el task file (obligatorio).
    Los demás artefactos se incluyen solo si existen.
    """
    role = config.roles.get(role_name)
    if role is None:
        raise PromptError(
            f"rol '{role_name}' no existe — definidos: {sorted(config.roles)}"
        )

    repo_root = Path(repo_root)
    if orchestra_root is None:
        # src/orchestra/core/prompt_builder.py → parents[3] = raíz de orchestra
        orchestra_root = Path(__file__).resolve().parents[3]
    orchestra_root = Path(orchestra_root)

    # El planner PRODUCE la tarea; builder/tester la CONSUMEN.
    produces_task = role_name == "planner"
    task_path = repo_root / "progress" / f"task_{slug}.md"
    task_body = _read(task_path)
    if task_body is None and not produces_task:
        raise PromptError(f"no existe el task file obligatorio: {task_path}")

    parts: list[str] = [
        f"Eres el rol '{role_name}' del ciclo TDD. Sigue el contrato de la sección ROL "
        f"al pie de la letra. Las RULES son no negociables. Trabaja sobre la TAREA y los "
        f"artefactos que siguen.",
    ]

    # Contrato del rol.
    role_md = _read(orchestra_root / role.prompt)
    if role_md is None:
        raise PromptError(f"no encuentro el contrato del rol: {orchestra_root / role.prompt}")
    parts.append(_section("ROL", strip_frontmatter(role_md)))

    # Rules de implementación (siempre).
    rules_dir = orchestra_root / "src" / "orchestra" / "rules"
    for rule in _ALWAYS_RULES:
        body = _read(rules_dir / f"{rule}.md")
        if body is not None:
            parts.append(_section(f"RULE — {rule}", strip_frontmatter(body)))

    # Rules condicionales al stack del repo target (p. ej. Python → 30-python-playwright).
    for rule, markers in _STACK_RULES.items():
        if any((repo_root / m).exists() for m in markers):
            body = _read(rules_dir / f"{rule}.md")
            if body is not None:
                parts.append(_section(f"RULE — {rule}", strip_frontmatter(body)))

    # Skill engram-memory (si orchestra la trae).
    engram = _read(orchestra_root / "src" / "orchestra" / "skills" / "engram-memory.md")
    if engram is not None:
        parts.append(_section("SKILL — engram-memory", strip_frontmatter(engram)))

    # Skills disciplinarias asignadas a este rol (security-review, self-critique…).
    skills_dir = orchestra_root / "src" / "orchestra" / "skills"
    for skill in role.skills:
        body = _read(skills_dir / f"{skill}.md")
        if body is not None:
            parts.append(_section(f"SKILL — {skill}", strip_frontmatter(body)))

    # Estado del repo target (opcionales).
    for title, rel in [
        ("REPO — CLAUDE.md", "CLAUDE.md"),
        ("REPO — ARCHITECTURE.md", "ARCHITECTURE.md"),
        ("CONTEXT — active-task", "context/active-task.md"),
    ]:
        body = _read(repo_root / rel)
        if body is not None:
            parts.append(_section(title, body))

    if produces_task:
        # El planner lee la documentación de planificación y PRODUCE la tarea.
        for title, rel in [
            ("ROADMAP — PHASE_PLAN", "PHASE_PLAN.md"),
            ("FASE ACTIVA — active-phase", "context/active-phase.md"),
        ]:
            body = _read(repo_root / rel)
            if body is not None:
                parts.append(_section(title, body))
        # Si ya hay un task file (re-planteo tras BLOCKED), lo incluye como referencia.
        if task_body is not None:
            parts.append(_section(f"TAREA PREVIA — task_{slug}", task_body))
    else:
        # builder/tester: la tarea (obligatoria) + artefactos del ciclo (opcionales).
        parts.append(_section(f"TAREA — task_{slug}", task_body))
        for title, rel in [
            (f"TESTS — tests_{slug}", f"progress/tests_{slug}.md"),
            (f"BUILDER — builder_{slug}", f"progress/builder_{slug}.md"),
            (f"ACEPTACIÓN PREVIA — acceptance_{slug}", f"progress/acceptance_{slug}.md"),
        ]:
            body = _read(repo_root / rel)
            if body is not None:
                parts.append(_section(title, body))

    parts.append(f"\n\n---\n\nEjecuta ahora la tarea como rol '{role_name}'.")
    return "".join(parts)
