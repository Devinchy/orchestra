"""Tests RED para core/scaffold.py — `orchestra init` prepara un repo target.

Crea la estructura que el ciclo necesita (progress/, context/, orchestra.toml,
PHASE_PLAN.md) y añade progress/ a .gitignore. Idempotente: no sobrescribe.
"""
from __future__ import annotations

from orchestra.core import scaffold


def test_init_crea_la_estructura(tmp_path):
    res = scaffold.init_repo(tmp_path)
    assert (tmp_path / "progress").is_dir()
    assert (tmp_path / "context" / "active-phase.md").is_file()
    assert (tmp_path / "context" / "active-task.md").is_file()
    assert (tmp_path / "orchestra.toml").is_file()
    assert (tmp_path / "PHASE_PLAN.md").is_file()
    assert any("orchestra.toml" in c for c in res.created)


def test_init_anade_progress_a_gitignore(tmp_path):
    scaffold.init_repo(tmp_path)
    gi = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "progress/" in gi


def test_init_no_duplica_gitignore(tmp_path):
    (tmp_path / ".gitignore").write_text("progress/\n.venv/\n", encoding="utf-8")
    scaffold.init_repo(tmp_path)
    gi = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert gi.count("progress/") == 1          # no se duplica


def test_init_es_idempotente_no_sobrescribe(tmp_path):
    (tmp_path / "PHASE_PLAN.md").write_text("# mi roadmap propio", encoding="utf-8")
    res = scaffold.init_repo(tmp_path)
    # no se toca el PHASE_PLAN existente
    assert (tmp_path / "PHASE_PLAN.md").read_text(encoding="utf-8") == "# mi roadmap propio"
    assert any("PHASE_PLAN.md" in s for s in res.skipped)


def test_init_autodetecta_pytest(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'", encoding="utf-8")
    scaffold.init_repo(tmp_path)
    toml = (tmp_path / "orchestra.toml").read_text(encoding="utf-8")
    assert "pytest" in toml


def test_init_test_command_override(tmp_path):
    scaffold.init_repo(tmp_path, test_command="make test")
    toml = (tmp_path / "orchestra.toml").read_text(encoding="utf-8")
    assert "make test" in toml
