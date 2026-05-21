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
