"""CLI de orchestra.

  orchestra run <role> --slug X [--provider P] [--model M]
  orchestra status

La lógica vive en core/; el CLI solo parsea args, lee el entorno, llama al runner
y presenta el resultado. Errores de config/routing/prompt se muestran limpios.
"""
from __future__ import annotations

import os
from pathlib import Path

import click

from orchestra.core import config as cfg
from orchestra.core import cycle as cycle_core
from orchestra.core import runner

# Raíz de la instalación de orchestra (src/orchestra/cli.py → parents[2]).
ORCHESTRA_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ORCHESTRA_ROOT / "config"

DEFAULT_PROXY_URL = "http://localhost:4000"
DEFAULT_MASTER_KEY = "sk-local-orchestra"


@click.group()
def main() -> None:
    """orchestra — orquestador multi-modelo del ciclo TDD (planner/builder/tester)."""


def _fmt_tokens(usage: dict) -> str:
    n = usage.get("completion_tokens") or usage.get("total_tokens")
    if not n:
        return ""
    return f" · {n/1000:.1f}k tok" if n >= 1000 else f" · {n} tok"


def _progress(event: str, **d) -> None:
    """Imprime el progreso en vivo (ASCII, sin depender de la codificación de consola)."""
    if event == "role_start":
        click.echo(f"  > {d['role']} ...", nl=False)
    elif event == "role_done":
        click.echo(f"  {d['provider']}/{d['model']}  "
                   f"{d['elapsed_s']:.1f}s{_fmt_tokens(d.get('usage', {}))}")


@main.command()
@click.argument("role")
@click.option("--slug", required=True, help="Slug de la tarea (progress/task_<slug>.md).")
@click.option("--provider", default=None, help="Override del proveedor para esta corrida.")
@click.option("--model", default=None, help="Override del modelo para esta corrida.")
def run(role: str, slug: str, provider: str | None, model: str | None) -> None:
    """Ejecuta un ROL sobre una tarea, contra el proxy litellm local."""
    proxy_url = os.environ.get("LITELLM_PROXY_URL", DEFAULT_PROXY_URL)
    api_key = os.environ.get("LITELLM_MASTER_KEY", DEFAULT_MASTER_KEY)

    try:
        config = cfg.load_config(CONFIG_DIR)
        result = runner.run_role(
            config, role, slug,
            repo_root=Path.cwd(),
            orchestra_root=ORCHESTRA_ROOT,
            proxy_url=proxy_url,
            api_key=api_key,
            provider_override=provider,
            model_override=model,
            on_event=_progress,
        )
    except Exception as e:  # noqa: BLE001 — UX: mensaje limpio, no traceback
        raise click.ClickException(str(e)) from e

    click.echo("-" * 50)
    click.echo(f"  rol:        {result.role}")
    click.echo(f"  proveedor:  {result.provider}")
    click.echo(f"  modelo:     {result.model}")
    click.echo(f"  gate PII:   {result.gate_action}")
    if result.gate_action != "pass":
        click.echo(f"              {result.gate_reason}")
    if result.pii_paths:
        click.echo(f"  paths PII:  {', '.join(result.pii_paths)}")
    click.echo(f"  duración:   {result.elapsed_s:.1f}s{_fmt_tokens(result.usage)}")
    if result.files_changed:
        click.echo(f"  archivos:   {', '.join(result.files_changed)}")
    click.echo(f"  transcript: {result.transcript_path}")
    click.echo("-" * 50)


@main.command(name="cycle")
@click.option("--slug", required=True, help="Slug de la tarea.")
@click.option("--planner", default=None, help="Proveedor para el rol planner.")
@click.option("--builder", default=None, help="Proveedor para el rol builder.")
@click.option("--tester", default=None, help="Proveedor para el rol tester.")
@click.option("--all", "all_provider", default=None,
              help="Mismo proveedor para los 3 roles (atajo).")
@click.option("--max-iters", default=3, show_default=True, help="Tope de vueltas builder->tester.")
def cycle_cmd(slug, planner, builder, tester, all_provider, max_iters) -> None:
    """Ejecuta el ciclo completo planner -> builder -> tester con routing del veredicto."""
    proxy_url = os.environ.get("LITELLM_PROXY_URL", DEFAULT_PROXY_URL)
    api_key = os.environ.get("LITELLM_MASTER_KEY", DEFAULT_MASTER_KEY)

    if all_provider:
        overrides = {"planner": all_provider, "builder": all_provider, "tester": all_provider}
    else:
        overrides = {r: p for r, p in
                     [("planner", planner), ("builder", builder), ("tester", tester)]
                     if p is not None}

    try:
        config = cfg.load_config(CONFIG_DIR)
        result = cycle_core.run_cycle(
            config, slug,
            repo_root=Path.cwd(), orchestra_root=ORCHESTRA_ROOT,
            proxy_url=proxy_url, api_key=api_key,
            provider_overrides=overrides, max_iters=max_iters,
            on_event=_progress,
        )
    except Exception as e:  # noqa: BLE001
        raise click.ClickException(str(e)) from e

    click.echo("=" * 50)
    click.echo(f"  CICLO {slug}")
    for i, step in enumerate(result.history, 1):
        click.echo(f"  {i}. {step.role:8} {step.provider}/{step.model}")
    click.echo("-" * 50)
    click.echo(f"  veredicto final: {result.final_status}")
    click.echo(f"  iteraciones:     {result.iterations}")
    click.echo(f"  parada:          {result.stopped_reason}")
    click.echo("=" * 50)
    if result.final_status != "PASS":
        raise SystemExit(1)


@main.command()
def status() -> None:
    """Muestra la tarea activa (context/active-task.md del repo actual)."""
    active = Path.cwd() / "context" / "active-task.md"
    if active.is_file():
        click.echo(active.read_text(encoding="utf-8"))
    else:
        click.echo("ninguna tarea activa — invoca el planner para generar una.")


@main.group()
def config() -> None:
    """Inspecciona la configuración de orchestra."""


@config.command(name="show")
def config_show() -> None:
    """Imprime la config resuelta: proveedores, roles, gate PII, backends del builder."""
    try:
        c = cfg.load_config(CONFIG_DIR)
    except Exception as e:  # noqa: BLE001
        raise click.ClickException(str(e)) from e

    click.echo("PROVEEDORES (modelo default · DPA):")
    for name, p in c.providers.items():
        dpa = "sí" if p.dpa_signed is True else (
            "self-hosted" if p.dpa_signed == "self_hosted" else "NO")
        click.echo(f"  {name:9} {p.default_model:18} dpa={dpa}")

    click.echo("\nROLES (provider/model por defecto):")
    for name, r in c.roles.items():
        click.echo(f"  {name:8} {r.default_provider}/{r.default_model}")

    click.echo(f"\nGATE PII: mode={c.routing.pii_gate.mode} "
               f"· fallback={c.routing.pii_gate.strict_fallback_provider}"
               f"/{c.routing.pii_gate.strict_fallback_model}")

    click.echo("\nBUILDER por proveedor (backend de ejecución):")
    for prov, backend in c.executors.builder_backend.items():
        via = " (via proxy)" if c.executors.backends[backend].via_proxy else ""
        click.echo(f"  {prov:9} -> {backend}{via}")


if __name__ == "__main__":
    main()
