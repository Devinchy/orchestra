"""Carga y validación de la configuración de orchestra.

Lee config/{providers,roles,routing}.toml con tomllib (stdlib) y los convierte en
dataclasses validadas. Sin dependencias externas — los tests del día 1 corren con
solo pytest instalado.

Filosofía: fallar rápido y claro. Un typo en la config (rol que apunta a un
provider inexistente, fallback PII a un provider sin DPA) debe reventar al cargar,
con un mensaje accionable, no a mitad de un ciclo TDD ya en marcha.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# dpa_signed admite bool o el literal "self_hosted" (open weights en máquina propia).
DpaStatus = bool | str

VALID_PII_MODES = {"advisory", "strict"}


class ConfigError(ValueError):
    """Config incoherente o malformada. El mensaje debe ser accionable."""


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    proxy_models: list[str]
    default_model: str
    supports_mcp: bool
    supports_tools: bool | str   # true | false | "limited"
    dpa_signed: DpaStatus

    @property
    def can_process_pii(self) -> bool:
        """True si este provider puede ver PII real según la política.

        DPA firmado (Anthropic) o self-hosted open-weights (Qwen/Ollama).
        """
        return self.dpa_signed is True or self.dpa_signed == "self_hosted"


@dataclass(frozen=True)
class RoleSpec:
    name: str
    prompt: str
    default_provider: str
    default_model: str
    tools: list[str]


@dataclass(frozen=True)
class PiiGateConfig:
    mode: str                       # "advisory" | "strict"
    sensitive_patterns_file: str
    strict_fallback_provider: str
    strict_fallback_model: str


@dataclass(frozen=True)
class RoutingConfig:
    pii_gate: PiiGateConfig
    fallback: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OrchestraConfig:
    providers: dict[str, ProviderSpec]
    roles: dict[str, RoleSpec]
    routing: RoutingConfig


def _load_toml(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"falta el archivo de config: {path}")
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _parse_providers(raw: dict) -> dict[str, ProviderSpec]:
    out: dict[str, ProviderSpec] = {}
    for name, spec in raw.get("providers", {}).items():
        try:
            out[name] = ProviderSpec(
                name=name,
                proxy_models=list(spec["proxy_models"]),
                default_model=spec["default_model"],
                supports_mcp=bool(spec["supports_mcp"]),
                supports_tools=spec["supports_tools"],
                dpa_signed=spec["dpa_signed"],
            )
        except KeyError as e:
            raise ConfigError(f"provider '{name}': falta el campo {e}") from e
    if not out:
        raise ConfigError("providers.toml no define ningún proveedor")
    return out


def _parse_roles(raw: dict) -> dict[str, RoleSpec]:
    out: dict[str, RoleSpec] = {}
    for name, spec in raw.get("roles", {}).items():
        try:
            out[name] = RoleSpec(
                name=name,
                prompt=spec["prompt"],
                default_provider=spec["default_provider"],
                default_model=spec["default_model"],
                tools=list(spec["tools"]),
            )
        except KeyError as e:
            raise ConfigError(f"rol '{name}': falta el campo {e}") from e
    if not out:
        raise ConfigError("roles.toml no define ningún rol")
    return out


def _parse_routing(raw: dict) -> RoutingConfig:
    gate = raw.get("pii_gate", {})
    try:
        fallback_block = gate["strict_fallback"]
        pii = PiiGateConfig(
            mode=gate["mode"],
            sensitive_patterns_file=gate.get("sensitive_patterns_file", ""),
            strict_fallback_provider=fallback_block["provider"],
            strict_fallback_model=fallback_block["model"],
        )
    except KeyError as e:
        raise ConfigError(f"routing.toml [pii_gate]: falta el campo {e}") from e

    return RoutingConfig(pii_gate=pii, fallback=dict(raw.get("fallback", {})))


def _validate(config: OrchestraConfig) -> None:
    providers = config.providers

    # 1. Cada rol apunta a un provider existente y a un modelo que ese provider expone.
    for role in config.roles.values():
        prov = providers.get(role.default_provider)
        if prov is None:
            raise ConfigError(
                f"rol '{role.name}': default_provider '{role.default_provider}' "
                f"no existe en providers.toml"
            )
        if role.default_model not in prov.proxy_models:
            raise ConfigError(
                f"rol '{role.name}': default_model '{role.default_model}' no está "
                f"en proxy_models de '{role.default_provider}' {prov.proxy_models}"
            )

    # 2. El modo del gate PII es válido.
    gate = config.routing.pii_gate
    if gate.mode not in VALID_PII_MODES:
        raise ConfigError(
            f"pii_gate.mode '{gate.mode}' inválido — usa uno de {sorted(VALID_PII_MODES)}"
        )

    # 3. El fallback del gate strict apunta a un provider que SÍ puede ver PII.
    fb = providers.get(gate.strict_fallback_provider)
    if fb is None:
        raise ConfigError(
            f"pii_gate.strict_fallback.provider '{gate.strict_fallback_provider}' "
            f"no existe en providers.toml"
        )
    if not fb.can_process_pii:
        raise ConfigError(
            f"pii_gate.strict_fallback apunta a '{fb.name}' que NO tiene DPA ni es "
            f"self_hosted — el fallback de PII debe poder procesar PII legalmente"
        )
    if gate.strict_fallback_model not in fb.proxy_models:
        raise ConfigError(
            f"pii_gate.strict_fallback.model '{gate.strict_fallback_model}' no está "
            f"en proxy_models de '{fb.name}'"
        )

    # 4. La cadena de fallback referencia solo providers conocidos.
    for src, dst in config.routing.fallback.items():
        if src not in providers:
            raise ConfigError(f"fallback: provider origen '{src}' no existe")
        if dst not in providers:
            raise ConfigError(f"fallback: provider destino '{dst}' no existe")


def load_config(config_dir: Path) -> OrchestraConfig:
    """Carga y valida los 3 TOML de config_dir. Lanza ConfigError si algo no cuadra."""
    config_dir = Path(config_dir)
    config = OrchestraConfig(
        providers=_parse_providers(_load_toml(config_dir / "providers.toml")),
        roles=_parse_roles(_load_toml(config_dir / "roles.toml")),
        routing=_parse_routing(_load_toml(config_dir / "routing.toml")),
    )
    _validate(config)
    return config
