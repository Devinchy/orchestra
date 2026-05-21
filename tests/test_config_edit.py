"""Tests RED para core/config_edit.py — `orchestra config set` preservando comentarios."""
from __future__ import annotations

import pytest

from orchestra.core import config_edit


SAMPLE = """# comentario de cabecera
[roles.builder]
default_provider = "claude"   # comentario inline
default_model = "claude-sonnet-4-6"
"""


def test_set_cambia_el_valor(tmp_path):
    f = tmp_path / "roles.toml"
    f.write_text(SAMPLE, encoding="utf-8")
    config_edit.set_value(f, "roles.builder.default_provider", "codex")
    text = f.read_text(encoding="utf-8")
    assert 'default_provider = "codex"' in text


def test_set_preserva_comentarios(tmp_path):
    f = tmp_path / "roles.toml"
    f.write_text(SAMPLE, encoding="utf-8")
    config_edit.set_value(f, "roles.builder.default_provider", "codex")
    text = f.read_text(encoding="utf-8")
    assert "# comentario de cabecera" in text
    assert "# comentario inline" in text


def test_set_clave_inexistente_falla(tmp_path):
    f = tmp_path / "roles.toml"
    f.write_text(SAMPLE, encoding="utf-8")
    with pytest.raises(config_edit.ConfigEditError, match="nope"):
        config_edit.set_value(f, "roles.builder.nope", "x")


def test_set_archivo_inexistente_falla(tmp_path):
    with pytest.raises(config_edit.ConfigEditError):
        config_edit.set_value(tmp_path / "noexiste.toml", "a.b", "x")
