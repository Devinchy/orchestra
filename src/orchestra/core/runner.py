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
ExecutorFactory = Callable[[str], Executor]

# Errores que cuentan como caída transitoria de infraestructura (→ disparan fallback):
# proxy caído / status != 2xx (InvocationError), CLI no encontrado (OSError/FileNotFound).
_TRANSIENT_ERRORS = (_invoker.InvocationError, OSError)


class RunnerError(RuntimeError):
    """No se pudo ejecutar el rol: toda la cadena de fallback de proveedores falló."""


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
    """Elige el executor: builder con backend CLI configurado → CliExecutor; resto → Proxy.

    Backends `via_proxy` (ej. aider con modelos open) reciben env apuntando al proxy
    litellm, para hablar con él como si fuera OpenAI — sin keys propias del proveedor.
    """
    if role == "builder":
        backend_name = config.executors.builder_backend.get(provider)
        if backend_name:
            backend = config.executors.backends[backend_name]
            env = (
                {"OPENAI_API_BASE": proxy_url, "OPENAI_API_KEY": api_key}
                if backend.via_proxy else None
            )
            return CliExecutor(backend.command_template, env=env)
    return ProxyExecutor(proxy_url=proxy_url, api_key=api_key, invoke_fn=invoke_fn)


def _provider_chain(config: OrchestraConfig, provider: str, *, max_len: int = 4) -> list[str]:
    """[provider, fallback1, fallback2, ...] siguiendo routing.fallback, sin ciclos."""
    chain = [provider]
    seen = {provider}
    cur = provider
    while len(chain) < max_len:
        nxt = config.routing.fallback.get(cur)
        if not nxt or nxt in seen:
            break
        chain.append(nxt)
        seen.add(nxt)
        cur = nxt
    return chain


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
    executor_factory: ExecutorFactory | None = None,
    run_tests_fn: Callable[..., test_runner.TestRun] = test_runner.run_tests,
    patterns: list[str] | None = None,
) -> RunResult:
    """Ejecuta un rol sobre una tarea, end-to-end, con fallback por caída de proveedor."""
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

    # 3. Prompt del rol.
    prompt = prompt_builder.build_prompt(
        config, role, slug, repo_root=repo_root, orchestra_root=orchestra_root
    )

    # 4. El tester re-ejecuta los tests reales y los mete en su contexto.
    if role == "tester":
        run = run_tests_fn(repo_root)
        if run.command is not None:
            prompt += (
                f"\n\n=== TESTS RE-EJECUTADOS (output real) ===\n\n"
                f"comando: {run.command}\n"
                f"éxito: {run.success}\n\n{run.output}\n"
            )

    # 5. Determina la cadena de ejecución y la fábrica de executors.
    #    Con un executor concreto inyectado, NO hay fallback (un intento).
    if executor is not None:
        chain = [provider]
        make_executor: ExecutorFactory = lambda _prov: executor  # noqa: E731
    else:
        chain = _provider_chain(config, provider)
        make_executor = executor_factory or (
            lambda prov: _select_executor(
                config, role, prov,
                proxy_url=proxy_url, api_key=api_key, invoke_fn=invoke_fn,
            )
        )

    # 6. Intenta la cadena: gate PII por provider, ejecuta, fallback si cae (transitorio).
    errors: list[str] = []
    for i, prov in enumerate(chain):
        model_p = model if i == 0 else config.providers[prov].default_model
        decision = routing.apply_pii_gate(config, prov, model_p, touches_pii=touches_pii)
        eff_provider, eff_model = decision.provider, decision.model
        try:
            result = make_executor(eff_provider).execute(
                prompt, model=eff_model, repo_root=repo_root, role=role, slug=slug
            )
        except _TRANSIENT_ERRORS as e:
            errors.append(f"{eff_provider}: {e}")
            continue
        break
    else:
        raise RunnerError(
            f"toda la cadena de fallback falló para el rol '{role}': " + " | ".join(errors)
        )

    # 7. Captura de transcript.
    tpath = transcript.append_transcript(repo_root, slug, role, eff_provider, result.content)

    return RunResult(
        role=role,
        provider=eff_provider,
        model=eff_model,
        gate_action=decision.action,
        gate_reason=decision.reason,
        pii_paths=pii_paths,
        content=result.content,
        transcript_path=tpath,
        files_changed=result.files_changed,
    )
