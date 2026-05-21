"""runner — el pegamento end-to-end de un rol.

Encadena:
  routing.resolve_role_model   → (provider, model) (+ overrides).
  pii.task_touches_pii         → ¿la tarea toca PII?
  routing.apply_pii_gate       → gate (puede rebotar a un provider con DPA).
  prompt_builder.build_prompt  → el prompt del rol.
  [tester] test_runner.run_tests → corre los tests reales y los añade al prompt.
  Executor.execute             → ProxyExecutor (planner/tester) o CliExecutor (builder).
  transcript.append_transcript → captura del output.

El Executor se auto-selecciona por rol/proveedor; inyectable para tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from orchestra.core import invoker as _invoker
from orchestra.core import pii, prompt_builder, routing, transcript
from orchestra.core.config import OrchestraConfig
from orchestra.core.executors.base import Executor
from orchestra.core.executors.cli import CliExecutor
from orchestra.core.executors.proxy import ProxyExecutor
from orchestra.core.executors import test_runner

InvokeFn = Callable[..., _invoker.InvocationResult]


@dataclass(frozen=True)
class RunResult:
    role: str
    provider: str
    model: str
    gate_action: str
    gate_reason: str
    pii_paths: list[str]
    content: str
    transcript_path: Path
    files_changed: list[str] = field(default_factory=list)


def _select_executor(
    config: OrchestraConfig,
    role: str,
    provider: str,
    *,
    proxy_url: str,
    api_key: str,
    invoke_fn: InvokeFn,
) -> Executor:
    """Elige el executor: builder con backend CLI configurado → CliExecutor; resto → Proxy."""
    if role == "builder":
        backend_name = config.executors.builder_backend.get(provider)
        if backend_name:
            backend = config.executors.backends[backend_name]
            return CliExecutor(backend.command_template)
    return ProxyExecutor(proxy_url=proxy_url, api_key=api_key, invoke_fn=invoke_fn)


def run_role(
    config: OrchestraConfig,
    role: str,
    slug: str,
    *,
    repo_root: str | Path,
    orchestra_root: str | Path | None = None,
    proxy_url: str,
    api_key: str,
    provider_override: str | None = None,
    model_override: str | None = None,
    invoke_fn: InvokeFn = _invoker.invoke,
    executor: Executor | None = None,
    run_tests_fn: Callable[..., test_runner.TestRun] = test_runner.run_tests,
    patterns: list[str] | None = None,
) -> RunResult:
    """Ejecuta un rol sobre una tarea, end-to-end."""
    repo_root = Path(repo_root)

    # 1. Modelo según rol + overrides.
    provider, model = routing.resolve_role_model(
        config, role,
        provider_override=provider_override,
        model_override=model_override,
    )

    # 2. ¿La tarea toca PII?  (el planner produce la tarea; puede no existir aún)
    task_path = repo_root / "progress" / f"task_{slug}.md"
    if role != "planner" and not task_path.is_file():
        raise prompt_builder.PromptError(f"no existe el task file: {task_path}")
    touches_pii, pii_paths = (
        pii.task_touches_pii(task_path, patterns) if task_path.is_file() else (False, [])
    )

    # 3. Gate PII (puede cambiar provider/model).
    decision = routing.apply_pii_gate(config, provider, model, touches_pii=touches_pii)
    provider, model = decision.provider, decision.model

    # 4. Prompt del rol.
    prompt = prompt_builder.build_prompt(
        config, role, slug, repo_root=repo_root, orchestra_root=orchestra_root
    )

    # 5. El tester re-ejecuta los tests reales y los mete en su contexto.
    if role == "tester":
        run = run_tests_fn(repo_root)
        if run.command is not None:
            prompt += (
                f"\n\n=== TESTS RE-EJECUTADOS (output real) ===\n\n"
                f"comando: {run.command}\n"
                f"éxito: {run.success}\n\n{run.output}\n"
            )

    # 6. Executor (auto-seleccionado o inyectado).
    if executor is None:
        executor = _select_executor(
            config, role, provider,
            proxy_url=proxy_url, api_key=api_key, invoke_fn=invoke_fn,
        )
    result = executor.execute(
        prompt, model=model, repo_root=repo_root, role=role, slug=slug
    )

    # 7. Captura de transcript.
    tpath = transcript.append_transcript(repo_root, slug, role, provider, result.content)

    return RunResult(
        role=role,
        provider=provider,
        model=model,
        gate_action=decision.action,
        gate_reason=decision.reason,
        pii_paths=pii_paths,
        content=result.content,
        transcript_path=tpath,
        files_changed=result.files_changed,
    )
