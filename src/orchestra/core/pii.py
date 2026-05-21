"""Detección de paths que tocan PII.

Primer eslabón del gate PII: dado un conjunto de paths (típicamente los que una
tarea declara que va a tocar), decide cuáles casan con patrones sensibles. El gate
(routing.py) usa esto para decidir si rebota a un proveedor con DPA.

Los patrones por defecto replican los de auto-label-sensitive.yml del ecosistema
dev-config, para que el criterio de "esto es sensible" sea el mismo en todas partes.
El match es FULL match (^patrón$), igual que en el workflow.
"""
from __future__ import annotations

import re
from pathlib import Path

# Patrones genéricos. Cada repo puede ampliarlos vía routing.toml
# (sensitive_patterns_file) sin tocar este módulo.
DEFAULT_SENSITIVE_PATTERNS: list[str] = [
    # Auth / sesiones
    r".*[Aa]uth.*",
    r".*[Ll]ogin.*",
    r".*[Ss]ession.*",
    r".*[Tt]oken.*",
    # Secretos / credenciales
    r".*[Cc]redential.*",
    r".*[Ss]ecret.*",
    r".*\.pem$",
    r".*\.key$",
    r".*\.pfx$",
    r".*\.pkcs12$",
    r".*\.p12$",
    r"\.env.*",
    r"secrets/.*",
]


def paths_touch_pii(
    paths: list[str],
    patterns: list[str] | None = None,
) -> list[str]:
    """Devuelve los paths que casan con algún patrón sensible (full match).

    Args:
        paths: rutas candidatas (las que la tarea va a tocar).
        patterns: regex sensibles. Si None, usa DEFAULT_SENSITIVE_PATTERNS.

    Returns:
        Sublista de `paths` que casan, en el orden de entrada. Vacía si ninguno.
    """
    active = DEFAULT_SENSITIVE_PATTERNS if patterns is None else patterns
    compiled = [re.compile(f"^(?:{pat})$") for pat in active]

    matched: list[str] = []
    for path in paths:
        if any(rx.match(path) for rx in compiled):
            matched.append(path)
    return matched


# Heurística de extracción de paths desde un task file (réplica de detect-pii.sh).
_BACKTICK = re.compile(r"`([^`]+)`")
_SLASH_PATH = re.compile(r"[A-Za-z0-9_.\-]+/[A-Za-z0-9_./\-]+")
_EXT_FILE = re.compile(
    r"\.?[A-Za-z0-9_\-]+\.(?:py|ts|tsx|js|jsx|sh|ya?ml|json|env|pem|key|pfx|p12|pkcs12)\b"
)
_ENV_LIKE = re.compile(r"\.env[A-Za-z0-9_.\-]*")
_ENDS_IN_EXT = re.compile(r"\.[A-Za-z0-9]+$")


def extract_candidate_paths(text: str) -> set[str]:
    """Extrae tokens que parecen paths de un texto (task file).

    Generoso a propósito: un falso positivo solo da un gate más conservador.
    Capta: tokens entre backticks que parecen path/archivo, tokens con `/`,
    archivos con extensión de código, y dotfiles tipo `.env*`. Filtra URLs.
    """
    out: set[str] = set()

    for m in _BACKTICK.findall(text):
        token = m.strip()
        if "/" in token or _ENDS_IN_EXT.search(token):
            out.add(token)

    out.update(_SLASH_PATH.findall(text))
    out.update(_EXT_FILE.findall(text))
    out.update(_ENV_LIKE.findall(text))

    return {p for p in out if not p.startswith(("http://", "https://"))}


def task_touches_pii(
    task_path: str | Path,
    patterns: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """Lee un task file y decide si toca PII según sus paths candidatos.

    Returns (touches, matched_paths).
    """
    text = Path(task_path).read_text(encoding="utf-8")
    candidates = sorted(extract_candidate_paths(text))
    matched = paths_touch_pii(candidates, patterns)
    return (bool(matched), matched)
