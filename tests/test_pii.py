"""Tests RED para core/pii.py — detección de paths que tocan PII.

El gate PII de orchestra rebota tareas con PII a proveedores con DPA. El primer
eslabón es decidir si una tarea TOCA PII, comparando sus paths contra patrones
sensibles (mismos que el auto-label-sensitive de dev-config).
"""
from __future__ import annotations

from orchestra.core import pii


def test_path_normal_no_toca_pii():
    assert pii.paths_touch_pii(["src/utils/math.py", "README.md"]) == []


def test_path_con_auth_toca_pii():
    assert pii.paths_touch_pii(["src/auth/login.py"]) == ["src/auth/login.py"]


def test_extension_pem_toca_pii():
    assert pii.paths_touch_pii(["certs/server.pem"]) == ["certs/server.pem"]


def test_env_file_toca_pii():
    assert pii.paths_touch_pii([".env.production"]) == [".env.production"]


def test_devuelve_solo_los_sensibles_de_una_mezcla():
    paths = ["src/api/users.py", "src/session/store.py", "docs/readme.md"]
    # "session" casa con el patrón .*[Ss]ession.*
    assert pii.paths_touch_pii(paths) == ["src/session/store.py"]


def test_lista_vacia_devuelve_vacio():
    assert pii.paths_touch_pii([]) == []


def test_patrones_custom_sustituyen_a_los_default():
    # Con un patrón custom que solo casa "secreto/", "auth" deja de ser sensible.
    paths = ["src/auth/login.py", "secreto/clave.txt"]
    assert pii.paths_touch_pii(paths, patterns=["secreto/.*"]) == ["secreto/clave.txt"]


def test_match_es_full_match_no_substring():
    # El patrón .*\.pem$ exige terminar en .pem — "pem_notes.md" no debe casar.
    assert pii.paths_touch_pii(["docs/pem_notes.md"]) == []


def test_default_patterns_no_esta_vacio():
    assert len(pii.DEFAULT_SENSITIVE_PATTERNS) > 0


# ---------- extract_candidate_paths ----------

def test_extrae_paths_en_backticks():
    text = "Toca `src/auth/login.py` y `README.md`."
    got = pii.extract_candidate_paths(text)
    assert "src/auth/login.py" in got
    assert "README.md" in got


def test_extrae_paths_con_barra_sin_backticks():
    text = "- modificar src/api/users.py para añadir el endpoint"
    assert "src/api/users.py" in pii.extract_candidate_paths(text)


def test_extrae_archivo_con_extension_sin_directorio():
    text = "crea el archivo .env.production en la raíz"
    assert ".env.production" in pii.extract_candidate_paths(text)


def test_ignora_urls():
    text = "ver docs en https://example.com/guia"
    assert not any(p.startswith("http") for p in pii.extract_candidate_paths(text))


# ---------- task_touches_pii ----------

def test_task_touches_pii_true(tmp_path):
    task = tmp_path / "task_demo.md"
    task.write_text("Implementar `src/auth/session.py` con el token.", encoding="utf-8")
    touches, matched = pii.task_touches_pii(task)
    assert touches is True
    assert "src/auth/session.py" in matched


def test_task_touches_pii_false(tmp_path):
    task = tmp_path / "task_demo.md"
    task.write_text("Implementar `src/utils/math.py` con sumas.", encoding="utf-8")
    touches, matched = pii.task_touches_pii(task)
    assert touches is False
    assert matched == []
