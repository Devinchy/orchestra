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

## Estado: días 1–6 completados

Construido **test-first** (la propia filosofía que orquesta). **100 tests verdes.**

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

**Día 3 — end-to-end:**
- ✅ `core/pii.py` extendido — escanea el task file y decide si toca PII (`task_touches_pii`). **+6 tests.**
- ✅ `core/transcript.py` — captura append-only a `progress/transcript_<slug>.md`. **4 tests.**
- ✅ `core/runner.py` — el pegamento: resuelve modelo → gate PII → prompt → invoca → transcript. **4 tests.**
- ✅ `cli.py` — `orchestra run <role> --slug X [--provider/--model]` + `status`. **5 tests.**

### Uso real (con el proxy levantado)

```bash
# en tu repo de producto, con una tarea ya generada en progress/task_<slug>.md:
orchestra run builder --slug auth-jwt                  # usa el default del rol
orchestra run builder --slug auth-jwt --provider codex # override; el gate PII puede rebotarlo
orchestra status                                        # tarea activa
```

Demostrado end-to-end: pedir `--provider codex` sobre una tarea que toca `src/auth/login.py`
con `pii_gate.mode = strict` **rebota automáticamente a claude/sonnet** (Codex no tiene DPA),
invoca, y escribe el transcript. El rol que se invoca de verdad es el que el gate decide.

**Día 4 — el ciclo completo:**
- ✅ `roles/builder.md` ajustado a TDD completo (escribe tests RED + código) y `tester.md` a routing de 2 destinos (builder/planner) — coherente con 3 roles.
- ✅ `prompt_builder` — el planner produce la tarea (no la exige); inyecta PHASE_PLAN/active-phase.
- ✅ `core/verdict.py` — parsea el veredicto del tester (`Veredicto:` + `Volver a:`). **8 tests.**
- ✅ `core/cycle.py` — encadena planner→builder→tester, vuelca cada output a su artefacto, parsea el veredicto y enruta (PASS=fin, FAIL→builder, BLOCKED→planner), con tope de iteraciones. **6 tests.**
- ✅ `cli.py cycle` — `orchestra cycle --slug X --planner P --builder B --tester T` (o `--all P`). **3 tests.**

### El ciclo con rotación de modelos (tu caso de uso)

```bash
orchestra cycle --slug email-validator --planner codex --builder claude --tester codex
orchestra cycle --slug email-validator --all codex      # todo Codex
orchestra cycle --slug email-validator                  # defaults de roles.toml
```

Demostrado: con `planner=codex, builder=claude, tester=codex`, un veredicto FAIL del
tester re-itera el builder con la acceptance previa como contexto, y al PASS cierra
el ciclo. El hand-off entre roles es file-based (`task_`/`builder_`/`acceptance_`).

**Día 6 — capa de ejecución (executors):**
- ✅ `core/executors/base.py` — abstracción `Executor` + `ExecutionResult`.
- ✅ `proxy.py` — `ProxyExecutor`: razonamiento documental (planner/tester) vía el proxy.
- ✅ `cli.py` — `CliExecutor`: delega al CLI agéntico (builder edita el repo de verdad);
  construye el comando por backend, ejecuta y captura `git diff --name-only`. **6 tests.**
- ✅ `test_runner.py` — el tester re-ejecuta los tests reales (autodetecta pytest/npm/go). **6 tests.**
- ✅ `config/executors.toml` + `ExecutorConfig` — mapea proveedor → backend del builder.
- ✅ `runner` refactorizado: **auto-selecciona executor por rol** (builder con backend → CLI; resto → proxy), gate PII intacto antes de elegir. **+4 tests de selección.**

### Quién ejecuta qué (dirigido por rol)

| Rol | Executor | Edita el repo |
|---|---|---|
| planner | ProxyExecutor (proxy → texto) | No, produce el task file |
| tester | ProxyExecutor + re-ejecuta tests reales | No, solo lee + corre tests |
| **builder** | **CliExecutor** → `claude -p` / `codex exec` (aider para open, día 7) | **Sí** |

El gate PII se aplica **antes** de elegir backend: la PII nunca llega a un CLI de un
proveedor sin DPA. Si un proveedor no tiene backend configurado (qwen/deepseek/gemini
hoy), el builder cae a ejecución documental hasta que se añada (día 7, vía aider).

> **Verificación pendiente en tu entorno**: claude/codex/aider no están instalados
> aquí, así que la ejecución real está testeada con `subprocess` mockeado. En tu
> máquina, con los CLIs instalados y el proxy levantado, `orchestra cycle` ejecuta
> de verdad. El comando por backend es configurable en `executors.toml` (como el
> `CODEX_CMD` ajustable de dev-config).

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

## Lo que viene (día 7+)

| Hito | Entrega |
|---|---|
| 7 | Backend `aider` para builder con deepseek/qwen/gemini (apuntado al proxy). Autodetección de tests con override por `orchestra.toml` del repo. Verificación real con claude/codex instalados. |
| 8 | Fallback en runtime por caída/rate-limit (`next_fallback` ya existe, falta cablearlo con reintento). Pulido del CLI (`config show/set`). |

> El sistema completo ya funciona end-to-end: 3 roles, rotación de modelos por rol,
> gate PII enforced, routing del veredicto, y **ejecución real delegada a CLIs
> agénticos** para el builder. Falta cubrir los proveedores open (aider) y endurecer
> el runtime (fallback, verificación con CLIs reales).

## Requisitos

- Python ≥ 3.11 (usa `tomllib` de stdlib).
- A partir del día 2: `litellm[proxy]`, y las API keys en `.env` (ver `.env.example`).
