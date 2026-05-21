"""Estimación de coste de una llamada desde su `usage` (tokens) y las tarifas.

El coste es ESTIMADO: depende de que las tarifas de config/pricing.toml estén al
día. Si no hay tarifa para el modelo, devuelve None (no se inventa un número).
"""
from __future__ import annotations

from orchestra.core.config import PriceSpec


def estimate_cost(
    model: str,
    usage: dict,
    pricing: dict[str, PriceSpec],
) -> float | None:
    """USD estimados para una llamada. None si no hay tarifa para el modelo."""
    spec = pricing.get(model)
    if spec is None:
        return None
    inp = usage.get("prompt_tokens", 0) or 0
    out = usage.get("completion_tokens", 0) or 0
    return round(inp / 1e6 * spec.input + out / 1e6 * spec.output, 6)
