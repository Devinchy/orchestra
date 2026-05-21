"""Tests RED para core/cost.py — estimación de coste desde usage + tarifas."""
from __future__ import annotations

from orchestra.core import cost
from orchestra.core.config import PriceSpec


PRICING = {
    "claude-sonnet-4-6": PriceSpec(input=3.0, output=15.0),
    "qwen3-coder": PriceSpec(input=0.0, output=0.0),
}


def test_calcula_coste_input_y_output():
    usage = {"prompt_tokens": 1_000_000, "completion_tokens": 100_000}
    # 1M input * $3/M + 0.1M output * $15/M = 3.0 + 1.5 = 4.5
    assert cost.estimate_cost("claude-sonnet-4-6", usage, PRICING) == 4.5


def test_usage_pequeno():
    usage = {"prompt_tokens": 2000, "completion_tokens": 500}
    # 2000/1e6*3 + 500/1e6*15 = 0.006 + 0.0075 = 0.0135
    assert cost.estimate_cost("claude-sonnet-4-6", usage, PRICING) == 0.0135


def test_modelo_sin_tarifa_devuelve_none():
    assert cost.estimate_cost("modelo-desconocido", {"prompt_tokens": 100}, PRICING) is None


def test_usage_vacio_es_cero():
    assert cost.estimate_cost("claude-sonnet-4-6", {}, PRICING) == 0.0


def test_modelo_local_coste_cero():
    usage = {"prompt_tokens": 5000, "completion_tokens": 5000}
    assert cost.estimate_cost("qwen3-coder", usage, PRICING) == 0.0
