"""CliExecutor — delega la ejecución a un CLI agéntico (claude_code, codex_cli, aider).

Para el builder, que SÍ edita el repo. orchestra ya resolvió modelo + gate PII;
aquí solo se invoca el CLI apropiado en el repo target y se captura qué tocó
(vía `git diff --name-only`). subprocess y git son inyectables para tests — la
ejecución real (claude/codex de verdad) la verifica el usuario en su entorno.
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from orchestra.core.executors.base import CmdResult, ExecutionResult


def _resolve_exe(name: str) -> str:
    """Resuelve el ejecutable respetando PATHEXT.

    En Windows, npm instala los CLIs como shims `.CMD` (claude.CMD, aider, etc.),
    y subprocess no los encuentra por el nombre "a secas" (busca .exe). shutil.which
    sí los resuelve. Devuelve la ruta completa, o el nombre original si no se halla
    (para que el error sea claro).
    """
    return shutil.which(name) or name


def _default_run(
    argv: list[str], *, cwd: Path, stdin_text: str | None, env: dict | None = None
) -> CmdResult:
    full_env = {**os.environ, **env} if env else None
    resolved = [_resolve_exe(argv[0]), *argv[1:]]
    proc = subprocess.run(
        resolved, cwd=str(cwd), input=stdin_text,
        capture_output=True, text=True, env=full_env,
    )
    return CmdResult(returncode=proc.returncode, stdout=(proc.stdout or "") + (proc.stderr or ""))


def _default_git_changed(repo_root: Path) -> list[str]:
    git = _resolve_exe("git")
    try:
        tracked = subprocess.run(
            [git, "diff", "--name-only"], cwd=str(repo_root),
            capture_output=True, text=True,
        ).stdout.splitlines()
        untracked = subprocess.run(
            [git, "ls-files", "--others", "--exclude-standard"], cwd=str(repo_root),
            capture_output=True, text=True,
        ).stdout.splitlines()
        return [p for p in (*tracked, *untracked) if p.strip()]
    except (OSError, subprocess.SubprocessError):
        return []


RunCmd = Callable[..., CmdResult]
GitChanged = Callable[[Path], list[str]]


class CliExecutor:
    def __init__(
        self,
        command_template: str,
        *,
        env: dict | None = None,
        run_cmd: RunCmd = _default_run,
        git_changed: GitChanged = _default_git_changed,
    ) -> None:
        self.command_template = command_template
        self.env = env or {}
        self._run = run_cmd
        self._git_changed = git_changed

    def build_command(
        self, model: str, prompt: str
    ) -> tuple[list[str], str | None, str | None]:
        """Construye (argv, stdin_text, prompt_file).

        Si la plantilla tiene {prompt_file}, escribe el prompt a un temporal y lo
        sustituye (stdin=None). Si no, el prompt va por stdin.

        El split del template se hace ANTES de sustituir, para que un path con
        backslashes (Windows) no pase por shlex (que los trataría como escape).
        """
        tokens = shlex.split(self.command_template)
        has_prompt_file = any("{prompt_file}" in t for t in tokens)

        prompt_file: str | None = None
        if has_prompt_file:
            fd = tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False, encoding="utf-8"
            )
            fd.write(prompt)
            fd.close()
            prompt_file = fd.name

        argv: list[str] = []
        for tok in tokens:
            tok = tok.replace("{model}", model)
            if "{prompt_file}" in tok:
                tok = tok.replace("{prompt_file}", prompt_file or "")
            argv.append(tok)

        stdin = None if has_prompt_file else prompt
        return argv, stdin, prompt_file

    def execute(
        self,
        prompt: str,
        *,
        model: str,
        repo_root: Path,
        role: str,
        slug: str,
    ) -> ExecutionResult:
        argv, stdin_text, _ = self.build_command(model, prompt)
        result = self._run(argv, cwd=repo_root, stdin_text=stdin_text, env=self.env or None)
        files = self._git_changed(repo_root)
        return ExecutionResult(
            content=result.stdout,
            files_changed=files,
            success=result.returncode == 0,
        )
