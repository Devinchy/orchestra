"""Tests RED para core/transcript.py — captura append-only del output del modelo.

Mismo formato que el log-session.py de dev-config: progress/transcript_<slug>.md con
un bloque por sesión y un sub-bloque `### HH:MM:SS · rol (provider)` por invocación.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from orchestra.core import transcript


def test_crea_archivo_con_header_si_no_existe(tmp_path):
    out = transcript.append_transcript(
        tmp_path, "demo", "builder", "codex", "contenido del modelo"
    )
    assert out == tmp_path / "progress" / "transcript_demo.md"
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# Transcript — demo")
    assert "contenido del modelo" in text


def test_incluye_rol_y_provider_en_el_subheader(tmp_path):
    out = transcript.append_transcript(
        tmp_path, "demo", "builder", "codex", "x",
        now=datetime(2026, 5, 20, 14, 30, 5),
    )
    text = out.read_text(encoding="utf-8")
    assert "14:30:05 · builder (codex)" in text


def test_append_only_acumula(tmp_path):
    transcript.append_transcript(tmp_path, "demo", "planner", "claude", "primera")
    out = transcript.append_transcript(tmp_path, "demo", "builder", "codex", "segunda")
    text = out.read_text(encoding="utf-8")
    assert "primera" in text
    assert "segunda" in text
    # Header una sola vez.
    assert text.count("# Transcript — demo") == 1


def test_crea_progress_dir_si_no_existe(tmp_path):
    # tmp_path sin progress/ todavía
    assert not (tmp_path / "progress").exists()
    transcript.append_transcript(tmp_path, "demo", "tester", "claude", "y")
    assert (tmp_path / "progress").is_dir()
