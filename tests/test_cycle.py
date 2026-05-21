"""Tests RED para core/cycle.py — encadenado de los 3 roles con routing del veredicto.

cycle.run_cycle ejecuta planner (si no hay tarea) → builder → tester, vuelca el
output de cada rol a su artefacto canónico, parsea el veredicto y enruta:
  PASS              → fin.
  Volver a builder  → re-ejecuta builder (con la acceptance previa como contexto).
  Volver a planner  → re-ejecuta planner.
Tope de iteraciones para no bucle infinito. run_fn inyectado (sin red).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from orchestra.core import config as cfg
from orchestra.core import cycle
from orchestra.core.runner import RunResult

ORCHESTRA_ROOT = Path(__file__).resolve().parents[1]
REPO_CONFIG = ORCHESTRA_ROOT / "config"


def _config():
    return cfg.load_config(REPO_CONFIG)


def _result(role, content, provider="claude", model="m", cost_usd=None, elapsed_s=0.0):
    return RunResult(role=role, provider=provider, model=model,
                     gate_action="pass", gate_reason="", pii_paths=[],
                     content=content, transcript_path=Path("t"),
                     cost_usd=cost_usd, elapsed_s=elapsed_s)


def test_cycle_agrega_coste_y_tiempo_total(tmp_path):
    repo = _repo(tmp_path)
    costs = {"planner": 0.02, "builder": 0.04, "tester": 0.03}

    def run_fn(config, role, slug, **kw):
        content = ("# Tarea" if role == "planner"
                   else "impl" if role == "builder"
                   else "Veredicto: PASS\nVolver a: ninguno")
        return _result(role, content, cost_usd=costs[role], elapsed_s=2.0)

    res = cycle.run_cycle(_config(), "demo", run_fn=run_fn, **_common_kwargs(repo))
    assert res.total_cost_usd == 0.09         # 0.02 + 0.04 + 0.03
    assert res.total_elapsed_s == 6.0         # 3 steps × 2.0


def test_cycle_total_cost_none_si_ningun_step_tiene_coste(tmp_path):
    repo = _repo(tmp_path)

    def run_fn(config, role, slug, **kw):
        content = ("# Tarea" if role == "planner"
                   else "impl" if role == "builder"
                   else "Veredicto: PASS\nVolver a: ninguno")
        return _result(role, content)        # cost_usd None

    res = cycle.run_cycle(_config(), "demo", run_fn=run_fn, **_common_kwargs(repo))
    assert res.total_cost_usd is None


def _scripted_run_fn(scripts: dict[str, list[str]]):
    """run_fn fake: para cada rol, devuelve los contents en orden de llamada.

    `scripts` mapea rol -> lista de outputs sucesivos. Registra la secuencia de
    roles invocados en `calls`.
    """
    calls: list[str] = []
    idx: dict[str, int] = {r: 0 for r in scripts}

    def run_fn(config, role, slug, **kw):
        calls.append(role)
        i = idx[role]
        idx[role] = i + 1
        return _result(role, scripts[role][i])

    run_fn.calls = calls  # type: ignore[attr-defined]
    return run_fn


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "progress").mkdir()
    (tmp_path / "context").mkdir()
    return tmp_path


def _common_kwargs(repo):
    return dict(repo_root=repo, orchestra_root=ORCHESTRA_ROOT,
                proxy_url="http://x", api_key="k")


# ---------- Camino feliz: planner -> builder -> tester PASS ----------

def test_ciclo_feliz_pasa_a_la_primera(tmp_path):
    repo = _repo(tmp_path)
    run_fn = _scripted_run_fn({
        "planner": ["# Tarea: demo\nCA-1: algo."],
        "builder": ["implementado, 3 passed"],
        "tester": ["Veredicto: PASS\nVolver a: ninguno\nbien"],
    })
    res = cycle.run_cycle(_config(), "demo", run_fn=run_fn, **_common_kwargs(repo))

    assert res.final_status == "PASS"
    assert run_fn.calls == ["planner", "builder", "tester"]
    # Los artefactos se volcaron a disco.
    assert (repo / "progress" / "task_demo.md").read_text(encoding="utf-8").startswith("# Tarea")
    assert (repo / "progress" / "builder_demo.md").exists()
    assert (repo / "progress" / "acceptance_demo.md").exists()


def test_salta_planner_si_ya_hay_task(tmp_path):
    repo = _repo(tmp_path)
    (repo / "progress" / "task_demo.md").write_text("# Tarea ya existente", encoding="utf-8")
    run_fn = _scripted_run_fn({
        "planner": ["NO DEBERÍA LLAMARSE"],
        "builder": ["impl"],
        "tester": ["Veredicto: PASS\nVolver a: ninguno"],
    })
    res = cycle.run_cycle(_config(), "demo", run_fn=run_fn, **_common_kwargs(repo))
    assert "planner" not in run_fn.calls
    assert res.final_status == "PASS"


# ---------- Routing: FAIL -> builder -> PASS ----------

def test_fail_vuelve_a_builder_y_luego_pasa(tmp_path):
    repo = _repo(tmp_path)
    run_fn = _scripted_run_fn({
        "planner": ["# Tarea: demo"],
        "builder": ["intento 1", "intento 2 corregido"],
        "tester": [
            "Veredicto: FAIL\nVolver a: builder\ncorrige X",
            "Veredicto: PASS\nVolver a: ninguno",
        ],
    })
    res = cycle.run_cycle(_config(), "demo", run_fn=run_fn, **_common_kwargs(repo))
    assert res.final_status == "PASS"
    # planner, builder, tester(FAIL), builder, tester(PASS)
    assert run_fn.calls == ["planner", "builder", "tester", "builder", "tester"]
    assert res.iterations == 2


# ---------- Routing: BLOCKED -> planner ----------

def test_blocked_vuelve_a_planner(tmp_path):
    repo = _repo(tmp_path)
    run_fn = _scripted_run_fn({
        "planner": ["# Tarea v1", "# Tarea v2 replanteada"],
        "builder": ["impl1", "impl2"],
        "tester": [
            "Veredicto: BLOCKED\nVolver a: planner\nscope ambiguo",
            "Veredicto: PASS\nVolver a: ninguno",
        ],
    })
    res = cycle.run_cycle(_config(), "demo", run_fn=run_fn, **_common_kwargs(repo))
    assert res.final_status == "PASS"
    assert run_fn.calls == ["planner", "builder", "tester", "planner", "builder", "tester"]


# ---------- Tope de iteraciones ----------

def test_para_en_max_iters_sin_pass(tmp_path):
    repo = _repo(tmp_path)
    run_fn = _scripted_run_fn({
        "planner": ["# Tarea"],
        "builder": ["i1", "i2", "i3", "i4"],
        "tester": [
            "Veredicto: FAIL\nVolver a: builder\n",
            "Veredicto: FAIL\nVolver a: builder\n",
            "Veredicto: FAIL\nVolver a: builder\n",
            "Veredicto: FAIL\nVolver a: builder\n",
        ],
    })
    res = cycle.run_cycle(_config(), "demo", run_fn=run_fn, max_iters=3,
                          **_common_kwargs(repo))
    assert res.final_status == "FAIL"
    assert res.iterations == 3
    assert res.stopped_reason == "max_iters"


# ---------- Overrides de modelo por rol ----------

def test_pasa_overrides_por_rol(tmp_path):
    repo = _repo(tmp_path)
    seen = {}

    def run_fn(config, role, slug, **kw):
        seen[role] = kw.get("provider_override")
        content = ("# Tarea" if role == "planner"
                   else "impl" if role == "builder"
                   else "Veredicto: PASS\nVolver a: ninguno")
        return _result(role, content)

    cycle.run_cycle(_config(), "demo", run_fn=run_fn,
                    provider_overrides={"planner": "codex", "builder": "claude", "tester": "codex"},
                    **_common_kwargs(repo))
    assert seen["planner"] == "codex"
    assert seen["builder"] == "claude"
    assert seen["tester"] == "codex"


def test_cycle_reenvia_on_event_a_cada_rol(tmp_path):
    repo = _repo(tmp_path)
    seen = {}

    def run_fn(config, role, slug, **kw):
        seen[role] = kw.get("on_event")
        content = ("# Tarea" if role == "planner"
                   else "impl" if role == "builder"
                   else "Veredicto: PASS\nVolver a: ninguno")
        return _result(role, content)

    cb = lambda *a, **k: None  # noqa: E731
    cycle.run_cycle(_config(), "demo", run_fn=run_fn, on_event=cb, **_common_kwargs(repo))
    assert seen["planner"] is cb
    assert seen["builder"] is cb
    assert seen["tester"] is cb
