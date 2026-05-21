"""Tests RED para core/verdict.py — parseo del veredicto del tester.

El tester devuelve un acceptance_<slug>.md que empieza con dos líneas literales:
    Veredicto: PASS | FAIL | BLOCKED
    Volver a: ninguno | builder | planner
El cycle parsea esto para enrutar. Debe ser robusto a mayúsculas/espacios.
"""
from __future__ import annotations

import pytest

from orchestra.core import verdict as v


def test_pass_volver_a_ninguno():
    res = v.parse_verdict("Veredicto: PASS\nVolver a: ninguno\n\nresto del informe")
    assert res.status == "PASS"
    assert res.return_to is None


def test_fail_volver_a_builder():
    res = v.parse_verdict("Veredicto: FAIL\nVolver a: builder\n")
    assert res.status == "FAIL"
    assert res.return_to == "builder"


def test_blocked_volver_a_planner():
    res = v.parse_verdict("Veredicto: BLOCKED\nVolver a: planner")
    assert res.status == "BLOCKED"
    assert res.return_to == "planner"


def test_robusto_a_mayusculas_y_espacios():
    res = v.parse_verdict("  veredicto :   pass  \n  volver a :  Ninguno ")
    assert res.status == "PASS"
    assert res.return_to is None


def test_lineas_en_cualquier_parte_del_texto():
    text = "# Acceptance\n\nbla bla\n\nVeredicto: FAIL\nVolver a: builder\n\nmás texto"
    res = v.parse_verdict(text)
    assert res.status == "FAIL"
    assert res.return_to == "builder"


def test_sin_veredicto_falla():
    with pytest.raises(v.VerdictError):
        v.parse_verdict("informe sin la línea de veredicto")


def test_veredicto_invalido_falla():
    with pytest.raises(v.VerdictError, match="QUIZAS"):
        v.parse_verdict("Veredicto: QUIZAS\nVolver a: builder")


def test_is_pass_helper():
    assert v.parse_verdict("Veredicto: PASS\nVolver a: ninguno").is_pass
    assert not v.parse_verdict("Veredicto: FAIL\nVolver a: builder").is_pass
