"""Parseo del veredicto del tester (progress/acceptance_<slug>.md).

El tester devuelve dos líneas literales al principio del informe:
    Veredicto: PASS | FAIL | BLOCKED
    Volver a: ninguno | builder | planner

El cycle parsea esto para enrutar. Parser tolerante a mayúsculas/espacios y a que
las líneas aparezcan en cualquier parte del texto.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

VALID_STATUS = {"PASS", "FAIL", "BLOCKED"}
VALID_RETURN = {"ninguno", "builder", "planner"}

_VERDICT_RE = re.compile(r"^\s*veredicto\s*:\s*(\w+)\s*$", re.IGNORECASE | re.MULTILINE)
_RETURN_RE = re.compile(r"^\s*volver\s+a\s*:\s*([\w-]+)\s*$", re.IGNORECASE | re.MULTILINE)


class VerdictError(ValueError):
    """El informe del tester no trae un veredicto parseable."""


@dataclass(frozen=True)
class Verdict:
    status: str               # PASS | FAIL | BLOCKED
    return_to: str | None     # None (ninguno) | "builder" | "planner"

    @property
    def is_pass(self) -> bool:
        return self.status == "PASS"


def parse_verdict(text_or_path: str | Path) -> Verdict:
    """Extrae el veredicto. Acepta el texto directo o un path a leer."""
    text = text_or_path
    if isinstance(text_or_path, Path):
        text = text_or_path.read_text(encoding="utf-8")
    elif isinstance(text_or_path, str) and "\n" not in text_or_path:
        # Podría ser un path a un archivo existente.
        p = Path(text_or_path)
        if p.is_file():
            text = p.read_text(encoding="utf-8")

    m = _VERDICT_RE.search(text)
    if not m:
        raise VerdictError("no encuentro la línea 'Veredicto: ...' en el informe del tester")
    status = m.group(1).upper()
    if status not in VALID_STATUS:
        raise VerdictError(f"veredicto '{status}' inválido — usa {sorted(VALID_STATUS)}")

    rm = _RETURN_RE.search(text)
    raw_return = rm.group(1).lower() if rm else "ninguno"
    if raw_return not in VALID_RETURN:
        raise VerdictError(f"'Volver a: {raw_return}' inválido — usa {sorted(VALID_RETURN)}")

    return Verdict(status=status, return_to=None if raw_return == "ninguno" else raw_return)
