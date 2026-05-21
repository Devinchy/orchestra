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
import threading
from pathlib import Path
from typing import Callable

from orchestra.core.executors import claude_stream
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
    argv: list[str], *, cwd: Path, stdin_text: str | None,
    env: dict | None = None, on_line: Callable[[str], None] | None = None,
    timeout: float | None = None,
) -> CmdResult:
    """Ejecuta el comando con streaming: lee stdout línea a línea y llama on_line.

    Usa Popen (no run) para emitir cada línea según llega — así el builder se ve
    en directo. El prompt se escribe a stdin en un hilo para no bloquear la lectura
    (evita deadlock si el proceso produce mucho output antes de consumir el stdin).
    Un watchdog mata el proceso si supera `timeout` segundos (evita que un CLI
    colgado bloquee el ciclo indefinidamente). encoding utf-8 explícito: en Windows
    el modo texto usa cp1252, que no puede codificar las flechas "→" del prompt.
    """
    full_env = {**os.environ, **env} if env else None
    resolved = [_resolve_exe(argv[0]), *argv[1:]]
    proc = subprocess.Popen(
        resolved, cwd=str(cwd),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", env=full_env, bufsize=1,
    )

    def _writer() -> None:
        try:
            if stdin_text is not None:
                proc.stdin.write(stdin_text)
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    writer = threading.Thread(target=_writer, daemon=True)
    writer.start()

    timed_out = {"flag": False}
    watchdog: threading.Timer | None = None
    if timeout is not None:
        def _kill() -> None:
            timed_out["flag"] = True
            proc.kill()
        watchdog = threading.Timer(timeout, _kill)
        watchdog.start()

    lines: list[str] = []
    for raw in proc.stdout:
        line = raw.rstrip("\n")
        lines.append(line)
        if on_line is not None:
            on_line(line)
    proc.wait()
    if watchdog is not None:
        watchdog.cancel()
    writer.join(timeout=1)

    if timed_out["flag"]:
        lines.append(f"[orchestra] proceso abortado: superó el timeout de {timeout}s")
        return CmdResult(returncode=-1, stdout="\n".join(lines))
    return CmdResult(returncode=proc.returncode, stdout="\n".join(lines))


def _default_git_changed(repo_root: Path) -> list[str]:
    git = _resolve_exe("git")
    try:
        tracked = subprocess.run(
            [git, "diff", "--name-only"], cwd=str(repo_root),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        ).stdout.splitlines()
        untracked = subprocess.run(
            [git, "ls-files", "--others", "--exclude-standard"], cwd=str(repo_root),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
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
        timeout: float | None = 600.0,
        run_cmd: RunCmd = _default_run,
        git_changed: GitChanged = _default_git_changed,
    ) -> None:
        self.command_template = command_template
        self.env = env or {}
        self.timeout = timeout
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
        on_event: Callable[..., None] | None = None,
    ) -> ExecutionResult:
        argv, stdin_text, _ = self.build_command(model, prompt)

        def _on_line(line: str) -> None:
            # Streaming en vivo: emite cada tool-call de Claude según llega.
            if on_event is None:
                return
            for call in claude_stream.tool_calls_in_line(line):
                on_event("tool_call", role=role, tool=call.tool, summary=call.summary)

        result = self._run(
            argv, cwd=repo_root, stdin_text=stdin_text,
            env=self.env or None, on_line=_on_line, timeout=self.timeout,
        )
        files = self._git_changed(repo_root)
        success = result.returncode == 0

        # Si el CLI emitió stream-json (Claude Code), extrae texto final + traza +
        # usage + coste real. Otros CLIs (codex/aider en texto plano) → stdout tal cual.
        lines = result.stdout.splitlines()
        if claude_stream.looks_like_stream_json(lines):
            parsed = claude_stream.parse_stream(lines)
            return ExecutionResult(
                content=parsed.result_text or result.stdout,
                files_changed=files,
                success=success,
                usage=parsed.usage,
                cost_usd=parsed.cost_usd,
                trace=parsed.trace,
            )
        return ExecutionResult(
            content=result.stdout,
            files_changed=files,
            success=success,
        )
