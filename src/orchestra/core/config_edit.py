"""Edición de config TOML preservando comentarios y formato (tomlkit).

`orchestra config set roles.builder.default_provider codex` cambia un valor sin
destruir los comentarios — a diferencia de tomllib, que solo lee. Solo modifica
claves que ya existen (no crea estructura nueva): cambiar config es ajustar, no
inventar.
"""
from __future__ import annotations

from pathlib import Path

import tomlkit


class ConfigEditError(ValueError):
    """No se pudo editar la config (archivo o clave inexistente)."""


def set_value(toml_path: str | Path, dotted_key: str, value: str) -> None:
    """Cambia `dotted_key` (ej 'roles.builder.default_provider') a `value` en el TOML.

    Preserva comentarios y formato. Falla si el archivo o la clave no existen.
    """
    path = Path(toml_path)
    if not path.is_file():
        raise ConfigEditError(f"no existe el archivo de config: {path}")

    doc = tomlkit.parse(path.read_text(encoding="utf-8"))

    parts = dotted_key.split(".")
    node = doc
    for key in parts[:-1]:
        if key not in node:
            raise ConfigEditError(f"clave '{dotted_key}': sección '{key}' no existe")
        node = node[key]

    leaf = parts[-1]
    if leaf not in node:
        raise ConfigEditError(f"clave '{dotted_key}': '{leaf}' no existe (config set no crea claves nuevas)")

    node[leaf] = value
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")
