# orchestra

> Orquestador multi-modelo para el ciclo TDD de 3 roles (**planner → builder → tester**)
> con rotación de frontier models por rol vía un proxy LiteLLM local.

Proyecto independiente. Inspirado conceptualmente en el ecosistema `dev-config`
(3 roles con responsabilidad estricta, artefactos file-based, gate PII), pero con
código propio — no comparte ficheros ni depende de él.

## Idea en una frase

Quieres poder decir "este ciclo lo corre Codex de planner, Claude de builder y
Codex de tester", o "todo Claude", o "todo Codex", o meter DeepSeek/Qwen/Gemini —
sin reescribir nada. Los 3 roles son fijos; el **modelo de cada rol es config**.

```bash
orchestra cycle --slug auth-jwt --planner codex --builder claude --tester codex
orchestra cycle --slug auth-jwt --all codex
orchestra run builder --slug auth-jwt --provider deepseek
```

## Arquitectura

La clave es separar dos capas que en dev-config iban juntas:

```
                   ┌──────────────────────────┐
                   │  litellm proxy (local)   │  ← localhost:4000
                   │  litellm.yaml            │     endpoint OpenAI-compatible
                   │  + MCP bridge (engram)   │     centraliza API keys + logging
                   └────────────┬─────────────┘
                                │ HTTP (OpenAI API)
        ┌───────────────────────┼────────────────────────┐
        ▼                       ▼                        ▼
  orchestra CLI          (futuro) Claude Code       (futuro) Codex CLI
  planner/builder/tester    apuntando al proxy         apuntando al proxy
```

- **Capa de modelos** = el proxy LiteLLM. Normaliza Claude/Codex/DeepSeek/Qwen/Gemini
  a una sola API OpenAI-compatible. orchestra le habla por HTTP — nunca importa
  litellm ni ve API keys directamente.
- **Capa de agentes** = orchestra. Decide quién es planner/builder/tester, qué
  modelo usa cada uno, y aplica el gate PII y la cadena de fallback.

## Configuración

Todo en `config/` (TOML), sin tocar código:

| Archivo | Qué define |
|---|---|
| `providers.toml` | Los proveedores: modelos expuestos, soporte MCP/tools, **`dpa_signed`** (gobierna el gate PII). |
| `roles.toml` | Los 3 roles: prompt, provider+model por defecto, tools permitidas. |
| `routing.toml` | Gate PII (`mode = advisory \| strict`), fallback del gate, cadena de fallback por caída. |

Rotar modelos = cambiar `default_provider`/`default_model` en `roles.toml` o pasar
overrides por CLI.

## Gate PII

Activo desde el día 1. Una tarea "toca PII" si sus paths casan con patrones
sensibles (`core/pii.py`, mismos que el `auto-label-sensitive` de dev-config).

- **`strict`** (default actual): tarea con PII + provider sin DPA → rebota al
  `strict_fallback` (un provider con DPA o self-hosted). Enforcement duro.
- **`advisory`**: avisa pero continúa (úsalo cuando los DPAs estén firmados).

`dpa_signed` puede ser `true` (DPA firmado, p. ej. Anthropic), `false` (sin DPA,
no ve PII en strict), o `"self_hosted"` (open-weights local como Qwen/Ollama →
permitido para PII por la política).

## Estado: días 1–2 completados

Construido **test-first** (la propia filosofía que orquesta). **44 tests verdes.**

**Día 1 — lógica de decisión (solo stdlib):**
- ✅ Scaffold: `pyproject.toml`, `justfile`, `.gitignore`, `.env.example`.
- ✅ Config: `providers.toml` (5 proveedores), `roles.toml` (3 roles), `routing.toml`.
- ✅ `core/pii.py` — detección de paths sensibles. **9 tests.**
- ✅ `core/config.py` — carga + validación TOML (tomllib + dataclasses). **8 tests.**
- ✅ `core/routing.py` — selección de modelo, gate PII, fallback. **13 tests.**

**Día 2 — capa de invocación + contenido:**
- ✅ `roles/{planner,builder,tester}.md` + `rules/{00,10,20,70}.md` propios de orchestra.
- ✅ `litellm.yaml` — proxy con los 5 proveedores + MCP bridge de Engram.
- ✅ `core/prompt_builder.py` — compone el prompt por rol (contrato + rules + artefactos del repo). **9 tests.**
- ✅ `core/invoker.py` — llamada OpenAI-compatible al proxy (httpx). **5 tests** (con `MockTransport`, sin red).

### Cómo correr los tests

```bash
./.venv/Scripts/python.exe -m pytest        # Windows / Git Bash → 44 passed
# o:  just test
```

### Cómo levantar el proxy (cuando tengas las API keys)

```bash
cp .env.example .env        # rellena ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.
just proxy                  # litellm --config litellm.yaml --port 4000
# verifica:  curl http://localhost:4000/health
```

## Lo que viene (días 3–5)

| Día | Entrega |
|---|---|
| 3 | `core/runner.py` + `orchestra run <role> --slug X` end-to-end (resuelve modelo → gate PII → prompt → invoca proxy → captura transcript). Hand-off file-based entre roles. |
| 4 | `orchestra cycle` (los 3 encadenados, leyendo el "Volver a" del tester). Verificación con DeepSeek + Qwen reales. |
| 5 | Gemini, fallback en runtime por caída de proveedor, pulido del CLI (`status`, `config set`). |

> Pieza que falta para el end-to-end: el **runner** (día 3) que une lo que ya existe
> — `routing` decide el modelo, `prompt_builder` arma el prompt, `invoker` llama al
> proxy. Solo falta el pegamento + captura de `progress/transcript_<slug>.md`.

## Requisitos

- Python ≥ 3.11 (usa `tomllib` de stdlib).
- A partir del día 2: `litellm[proxy]`, y las API keys en `.env` (ver `.env.example`).
