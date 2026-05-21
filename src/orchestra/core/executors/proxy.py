"""ProxyExecutor — ejecución documental vía el proxy litellm.

Para roles que razonan y devuelven texto (planner, tester): no editan el repo.
Envuelve invoker.invoke. El content devuelto ES el artefacto del rol.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from orchestra.core import invoker as _invoker
from orchestra.core.executors.base import ExecutionResult


class ProxyExecutor:
    def __init__(
        self,
        *,
        proxy_url: str,
        api_key: str,
        invoke_fn: Callable[..., _invoker.InvocationResult] = _invoker.invoke,
    ) -> None:
        self._proxy_url = proxy_url
        self._api_key = api_key
        self._invoke = invoke_fn

    def execute(
        self,
        prompt: str,
        *,
        model: str,
        repo_root: Path,
        role: str,
        slug: str,
    ) -> ExecutionResult:
        result = self._invoke(
            [{"role": "user", "content": prompt}],
            model=model,
            proxy_url=self._proxy_url,
            api_key=self._api_key,
        )
        return ExecutionResult(
            content=result.content, files_changed=[], success=True,
            usage=result.usage,
        )
