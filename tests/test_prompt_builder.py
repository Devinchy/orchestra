"""Tests RED para core/prompt_builder.py — composición del prompt por rol.

Generaliza el build-builder-prompt.sh de dev-config a cualquiera de los 3 roles:
concatena el contrato del rol + rules aplicables + artefactos de la tarea que existan
en el repo target. Strip de frontmatter para no enviar metadata al modelo.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from orchestra.core import config as cfg
from orchestra.core import prompt_builder as pb

ORCHESTRA_ROOT = Path(__file__).resolve().parents[1]
REPO_CONFIG = ORCHESTRA_ROOT / "config"


def _make_repo(tmp_path: Path, *, slug: str = "demo", with_tests: bool = False) -> Path:
    (tmp_path / "progress").mkdir()
    (tmp_path / "context").mkdir()
    (tmp_path / "progress" / f"task_{slug}.md").write_text(
        "# Tarea: demo\n\nCA-1: hacer algo verificable.\n", encoding="utf-8"
    )
    (tmp_path / "context" / "active-task.md").write_text(
        "# Tarea activa\nResumen: demo\n", encoding="utf-8"
    )
    if with_tests:
        (tmp_path / "progress" / f"tests_{slug}.md").write_text(
            "# Tests RED: demo\n\ntest_demo falla con ImportError.\n", encoding="utf-8"
        )
    return tmp_path


def _config():
    return cfg.load_config(REPO_CONFIG)


# ---------- Caso feliz ----------

def test_incluye_contrato_del_rol(tmp_path):
    repo = _make_repo(tmp_path)
    prompt = pb.build_prompt(_config(), "builder", "demo",
                             repo_root=repo, orchestra_root=ORCHESTRA_ROOT)
    assert "Rol: builder" in prompt
    assert "UN ÚNICO INTENTO" in prompt   # del builder.md real


def test_incluye_rules(tmp_path):
    repo = _make_repo(tmp_path)
    prompt = pb.build_prompt(_config(), "builder", "demo",
                             repo_root=repo, orchestra_root=ORCHESTRA_ROOT)
    assert "TDD estricto" in prompt        # de 20-testing.md
    assert "Secretos nunca en código" in prompt  # de 10-security.md


def test_incluye_el_task_file(tmp_path):
    repo = _make_repo(tmp_path)
    prompt = pb.build_prompt(_config(), "planner", "demo",
                             repo_root=repo, orchestra_root=ORCHESTRA_ROOT)
    assert "CA-1: hacer algo verificable" in prompt


def test_incluye_tests_si_existen(tmp_path):
    repo = _make_repo(tmp_path, with_tests=True)
    prompt = pb.build_prompt(_config(), "builder", "demo",
                             repo_root=repo, orchestra_root=ORCHESTRA_ROOT)
    assert "test_demo falla con ImportError" in prompt


def test_omite_artefactos_inexistentes_sin_romper(tmp_path):
    repo = _make_repo(tmp_path, with_tests=False)
    prompt = pb.build_prompt(_config(), "builder", "demo",
                             repo_root=repo, orchestra_root=ORCHESTRA_ROOT)
    # No hay tests_demo.md → no debe aparecer una sección de tests vacía ni petar.
    assert "tests_demo" not in prompt


# ---------- Errores ----------

def test_task_inexistente_falla(tmp_path):
    (tmp_path / "progress").mkdir()
    with pytest.raises(pb.PromptError, match="task"):
        pb.build_prompt(_config(), "builder", "noexiste",
                        repo_root=tmp_path, orchestra_root=ORCHESTRA_ROOT)


def test_rol_inexistente_falla(tmp_path):
    repo = _make_repo(tmp_path)
    with pytest.raises(pb.PromptError, match="reviewer"):
        pb.build_prompt(_config(), "reviewer", "demo",
                        repo_root=repo, orchestra_root=ORCHESTRA_ROOT)


# ---------- Strip de frontmatter ----------

def test_strip_frontmatter_quita_yaml():
    text = "---\nname: x\nmodel: y\n---\n\n# Cuerpo real\ncontenido"
    out = pb.strip_frontmatter(text)
    assert "name: x" not in out
    assert "# Cuerpo real" in out


def test_strip_frontmatter_sin_frontmatter_no_toca():
    text = "# Sin frontmatter\nlínea"
    assert pb.strip_frontmatter(text) == text
