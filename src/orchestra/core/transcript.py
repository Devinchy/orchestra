"""Captura append-only del output del modelo a progress/transcript_<slug>.md.

Mismo formato que el log-session.py de dev-config: un bloque por sesión y un
sub-bloque por invocación con timestamp, rol y provider. progress/ está en
.gitignore (posible PII), nunca al repo compartido.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

_HEADER = (
    "# Transcript — {slug}\n\n"
    "> Volcado append-only de las respuestas de los modelos (cualquier proveedor)\n"
    "> para esta tarea. Contiene texto del modelo: posible PII — `progress/` está\n"
    "> en `.gitignore`, nunca al repo compartido.\n"
)


def append_transcript(
    repo_root: str | Path,
    slug: str,
    role: str,
    provider: str,
    content: str,
    *,
    now: datetime | None = None,
) -> Path:
    """Añade el output de una invocación al transcript de la tarea.

    Crea el archivo (con header) y el directorio progress/ si no existen.
    Devuelve la ruta del transcript.
    """
    now = now or datetime.now()
    repo_root = Path(repo_root)
    progress = repo_root / "progress"
    progress.mkdir(parents=True, exist_ok=True)

    path = progress / f"transcript_{slug}.md"
    if not path.exists():
        path.write_text(_HEADER.format(slug=slug), encoding="utf-8")

    block = (
        f"\n---\n\n"
        f"## Sesión {now.strftime('%Y-%m-%d %H:%M')}\n\n"
        f"### {now.strftime('%H:%M:%S')} · {role} ({provider})\n\n"
        f"{content.strip()}\n"
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write(block)

    return path
