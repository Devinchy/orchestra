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
from orchestra.core import runner

# Raíz de la instalación de orchestra (src/orchestra/cli.py → parents[2]).
ORCHESTRA_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ORCHESTRA_ROOT / "config"

DEFAULT_PROXY_URL = "http://localhost:4000"
DEFAULT_MASTER_KEY = "sk-local-orchestra"


@click.group()
def main() -> None:
    """orchestra — orquestador multi-modelo del ciclo TDD (planner/builder/tester)."""


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
        )
    except Exception as e:  # noqa: BLE001 — UX: mensaje limpio, no traceback
        raise click.ClickException(str(e)) from e

    click.echo("─" * 50)
    click.echo(f"  rol:        {result.role}")
    click.echo(f"  proveedor:  {result.provider}")
    click.echo(f"  modelo:     {result.model}")
    click.echo(f"  gate PII:   {result.gate_action}")
    if result.gate_action != "pass":
        click.echo(f"              {result.gate_reason}")
    if result.pii_paths:
        click.echo(f"  paths PII:  {', '.join(result.pii_paths)}")
    click.echo(f"  transcript: {result.transcript_path}")
    click.echo("─" * 50)


@main.command()
def status() -> None:
    """Muestra la tarea activa (context/active-task.md del repo actual)."""
    active = Path.cwd() / "context" / "active-task.md"
    if active.is_file():
        click.echo(active.read_text(encoding="utf-8"))
    else:
        click.echo("ninguna tarea activa — invoca el planner para generar una.")


if __name__ == "__main__":
    main()
