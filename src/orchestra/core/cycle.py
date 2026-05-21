"""cycle — encadena los 3 roles con routing del veredicto del tester.

Flujo:
  1. Si no existe la tarea, corre el PLANNER → vuelca su output a task_<slug>.md.
  2. Bucle (hasta max_iters o PASS):
       BUILDER → builder_<slug>.md
       TESTER  → acceptance_<slug>.md
       parsea el veredicto:
         PASS              → fin.
         FAIL  (builder)   → re-itera el builder (lee la acceptance previa).
         BLOCKED (planner) → re-corre el planner y vuelve a iterar.

Hand-off file-based: el output (content) de cada rol se vuelca a su artefacto
canónico, que el siguiente rol lee vía prompt_builder. run_fn es inyectable (tests).

Límite conocido: orchestra compone prompts e invoca modelos; NO ejecuta tool-calls
(editar el repo). El "content" de cada rol ES su artefacto. La ejecución real de
herramientas (modelo tocando código) es un hito aparte.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from orchestra.core import runner, verdict
from orchestra.core.config import OrchestraConfig

# Artefacto canónico donde se vuelca el output de cada rol.
_ARTIFACT = {"planner": "task", "builder": "builder", "tester": "acceptance"}


@dataclass(frozen=True)
class CycleStep:
    role: str
    provider: str
    model: str
    artifact: Path
    cost_usd: float | None = None
    elapsed_s: float = 0.0


@dataclass(frozen=True)
class CycleResult:
    final_status: str               # PASS | FAIL | BLOCKED
    return_to: str | None
    iterations: int                 # nº de vueltas builder→tester
    stopped_reason: str             # "pass" | "max_iters"
    history: list[CycleStep] = field(default_factory=list)

    @property
    def total_cost_usd(self) -> float | None:
        """Suma del coste de los steps con coste conocido. None si ninguno lo tiene."""
        costs = [s.cost_usd for s in self.history if s.cost_usd is not None]
        return round(sum(costs), 6) if costs else None

    @property
    def total_elapsed_s(self) -> float:
        return round(sum(s.elapsed_s for s in self.history), 1)


def run_cycle(
    config: OrchestraConfig,
    slug: str,
    *,
    repo_root: str | Path,
    orchestra_root: str | Path | None = None,
    proxy_url: str,
    api_key: str,
    provider_overrides: dict[str, str] | None = None,
    model_overrides: dict[str, str] | None = None,
    run_fn: Callable[..., runner.RunResult] = runner.run_role,
    max_iters: int = 3,
    on_event: Callable[..., None] | None = None,
) -> CycleResult:
    repo_root = Path(repo_root)
    provider_overrides = provider_overrides or {}
    model_overrides = model_overrides or {}
    history: list[CycleStep] = []

    def _run(role: str) -> runner.RunResult:
        res = run_fn(
            config, role, slug,
            repo_root=repo_root, orchestra_root=orchestra_root,
            proxy_url=proxy_url, api_key=api_key,
            provider_override=provider_overrides.get(role),
            model_override=model_overrides.get(role),
            on_event=on_event,
        )
        artifact = _write_artifact(repo_root, role, slug, res.content)
        history.append(CycleStep(
            role, res.provider, res.model, artifact,
            cost_usd=res.cost_usd, elapsed_s=res.elapsed_s,
        ))
        return res

    # 1. Asegura que existe la tarea (planner la produce si falta).
    task_path = repo_root / "progress" / f"task_{slug}.md"
    if not task_path.is_file():
        _run("planner")

    # 2. Bucle builder → tester.
    iterations = 0
    while True:
        iterations += 1
        _run("builder")
        tester_res = _run("tester")
        v = verdict.parse_verdict(tester_res.content)

        if v.is_pass:
            return CycleResult("PASS", None, iterations, "pass", history)

        if iterations >= max_iters:
            return CycleResult(v.status, v.return_to, iterations, "max_iters", history)

        if v.return_to == "planner":
            _run("planner")          # replantea la tarea; siguiente iter re-construye
        # si return_to == "builder": el bucle vuelve a correr builder, que lee
        # acceptance_<slug>.md (escrito arriba) con las instrucciones de corrección.


def _write_artifact(repo_root: Path, role: str, slug: str, content: str) -> Path:
    name = _ARTIFACT[role]
    progress = repo_root / "progress"
    progress.mkdir(parents=True, exist_ok=True)
    path = progress / f"{name}_{slug}.md"
    path.write_text(content, encoding="utf-8")
    return path
