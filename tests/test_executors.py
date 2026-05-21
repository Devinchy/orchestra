"""Tests RED para core/executors/ — ProxyExecutor, CliExecutor.

ProxyExecutor: razonamiento documental (planner/tester) vía el invoker.
CliExecutor: delega al CLI agéntico (builder). Aquí mockeamos subprocess y git
diff — la ejecución real (claude/codex de verdad) la verifica el usuario en su
entorno; estos tests verifican que el comando se construye bien y que el resultado
(stdout + files_changed) se parsea bien.
"""
from __future__ import annotations

from pathlib import Path

from orchestra.core.executors.base import ExecutionResult, CmdResult
from orchestra.core.executors.proxy import ProxyExecutor
from orchestra.core.executors.cli import CliExecutor
from orchestra.core.invoker import InvocationResult


# ---------- ProxyExecutor ----------

def test_proxy_executor_devuelve_content_del_invoker():
    def fake_invoke(messages, *, model, proxy_url, api_key, tools=None, **kw):
        return InvocationResult(content="razonamiento del modelo", model=model)

    ex = ProxyExecutor(proxy_url="http://x", api_key="k", invoke_fn=fake_invoke)
    res = ex.execute("un prompt", model="claude-opus-4-7",
                     repo_root=Path("."), role="planner", slug="demo")
    assert isinstance(res, ExecutionResult)
    assert res.content == "razonamiento del modelo"
    assert res.files_changed == []
    assert res.success is True


def test_proxy_executor_propaga_usage():
    def fake_invoke(messages, *, model, proxy_url, api_key, tools=None, **kw):
        return InvocationResult(content="x", model=model,
                                usage={"prompt_tokens": 50, "completion_tokens": 12})

    ex = ProxyExecutor(proxy_url="http://x", api_key="k", invoke_fn=fake_invoke)
    res = ex.execute("p", model="m", repo_root=Path("."), role="planner", slug="d")
    assert res.usage["completion_tokens"] == 12


# ---------- CliExecutor: construcción del comando ----------

def test_cli_build_command_sustituye_model_y_usa_stdin():
    ex = CliExecutor("codex exec -m {model} --full-auto")
    argv, stdin, prompt_file = ex.build_command("gpt-5-codex", "EL PROMPT")
    assert argv == ["codex", "exec", "-m", "gpt-5-codex", "--full-auto"]
    assert stdin == "EL PROMPT"        # sin {prompt_file} → prompt por stdin
    assert prompt_file is None


def test_cli_build_command_claude_code():
    ex = CliExecutor("claude -p --model {model} --permission-mode acceptEdits")
    argv, stdin, _ = ex.build_command("claude-sonnet-4-6", "P")
    assert argv == ["claude", "-p", "--model", "claude-sonnet-4-6",
                    "--permission-mode", "acceptEdits"]
    assert stdin == "P"


def test_cli_build_command_con_prompt_file_escribe_temp(tmp_path):
    ex = CliExecutor("aider --model {model} --message-file {prompt_file}")
    argv, stdin, prompt_file = ex.build_command("deepseek-coder", "CONTENIDO")
    assert stdin is None                       # con {prompt_file} → no stdin
    assert prompt_file is not None
    assert Path(prompt_file).read_text(encoding="utf-8") == "CONTENIDO"
    assert prompt_file in argv


# ---------- CliExecutor: ejecución (subprocess + git mockeados) ----------

def test_cli_execute_captura_stdout_y_files_changed(tmp_path):
    calls = {}

    def fake_run(argv, *, cwd, stdin_text, env=None):
        calls["argv"] = argv
        calls["cwd"] = cwd
        calls["stdin"] = stdin_text
        return CmdResult(returncode=0, stdout="builder hizo X\n3 passed")

    def fake_git_changed(repo_root):
        return ["src/foo.py", "tests/test_foo.py"]

    ex = CliExecutor("codex exec -m {model}", run_cmd=fake_run, git_changed=fake_git_changed)
    res = ex.execute("PROMPT", model="gpt-5-codex",
                     repo_root=tmp_path, role="builder", slug="demo")

    assert res.success is True
    assert "3 passed" in res.content
    assert res.files_changed == ["src/foo.py", "tests/test_foo.py"]
    assert calls["argv"][0] == "codex"
    assert calls["cwd"] == tmp_path
    assert calls["stdin"] == "PROMPT"


def test_cli_execute_returncode_no_cero_es_fallo(tmp_path):
    def fake_run(argv, *, cwd, stdin_text, env=None):
        return CmdResult(returncode=1, stdout="boom")

    ex = CliExecutor("codex exec -m {model}", run_cmd=fake_run,
                     git_changed=lambda r: [])
    res = ex.execute("P", model="gpt-5-codex",
                     repo_root=tmp_path, role="builder", slug="demo")
    assert res.success is False
    assert "boom" in res.content


def test_resolve_exe_usa_shutil_which(monkeypatch):
    # En Windows, claude es claude.CMD; _resolve_exe debe devolver la ruta resuelta.
    from orchestra.core.executors import cli as cli_mod
    monkeypatch.setattr(cli_mod.shutil, "which",
                        lambda name: r"C:\npm\claude.CMD" if name == "claude" else None)
    assert cli_mod._resolve_exe("claude") == r"C:\npm\claude.CMD"
    # Si no se encuentra, devuelve el nombre original (para un error claro).
    assert cli_mod._resolve_exe("inexistente") == "inexistente"


def test_cli_execute_inyecta_env_al_subprocess(tmp_path):
    seen = {}

    def fake_run(argv, *, cwd, stdin_text, env=None):
        seen["env"] = env
        return CmdResult(returncode=0, stdout="ok")

    ex = CliExecutor(
        "aider --model openai/{model}",
        env={"OPENAI_API_BASE": "http://localhost:4000", "OPENAI_API_KEY": "sk-local"},
        run_cmd=fake_run, git_changed=lambda r: [],
    )
    ex.execute("P", model="deepseek-coder",
               repo_root=tmp_path, role="builder", slug="demo")
    assert seen["env"]["OPENAI_API_BASE"] == "http://localhost:4000"
    assert seen["env"]["OPENAI_API_KEY"] == "sk-local"
