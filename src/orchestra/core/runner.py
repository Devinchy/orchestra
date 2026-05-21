"""runner — el pegamento end-to-end de un rol.

Encadena las piezas ya testeadas por separado:

  routing.resolve_role_model   → qué (provider, model) corre el rol (+ overrides).
  pii.task_touches_pii         → ¿la tarea toca PII?
  routing.apply_pii_gate       → gate (puede rebotar a un provider con DPA).
  prompt_builder.build_prompt  → el prompt completo del rol.
  invoke_fn (invoker.invoke)   → llamada al proxy.
  transcript.append_transcript → captura del output.

invoke_fn es inyectable para tests (sin red).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from orchestra.core import pii, prompt_builder, routing, transcript
from orchestra.core import invoker as _invoker
from orchestra.core.config import OrchestraConfig

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
    patterns: list[str] | None = None,
) -> RunResult:
    """Ejecuta un rol sobre una tarea, end-to-end, y captura el resultado."""
    repo_root = Path(repo_root)

    # 1. Modelo según rol + overrides.
    provider, model = routing.resolve_role_model(
        config, role,
        provider_override=provider_override,
        model_override=model_override,
    )

    # 2. ¿La tarea toca PII?  (lee el task file — falla aquí si no existe)
    task_path = repo_root / "progress" / f"task_{slug}.md"
    if not task_path.is_file():
        raise prompt_builder.PromptError(f"no existe el task file: {task_path}")
    touches_pii, pii_paths = pii.task_touches_pii(task_path, patterns)

    # 3. Gate PII (puede cambiar provider/model).
    decision = routing.apply_pii_gate(config, provider, model, touches_pii=touches_pii)
    provider, model = decision.provider, decision.model

    # 4. Prompt del rol.
    prompt = prompt_builder.build_prompt(
        config, role, slug, repo_root=repo_root, orchestra_root=orchestra_root
    )

    # 5. Invocación al proxy.
    result = invoke_fn(
        [{"role": "user", "content": prompt}],
        model=model,
        proxy_url=proxy_url,
        api_key=api_key,
    )

    # 6. Captura de transcript.
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
    )
