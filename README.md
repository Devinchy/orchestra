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

## Estado: días 1–12 completados

Construido **test-first** (la propia filosofía que orquesta). **137 tests verdes.**

> **Verificado en vivo contra Claude real** (proxy + CLI): planner genera tarea,
> builder edita el repo y deja tests en verde, tester valida, ciclo cierra en PASS.
> Por el camino se arreglaron 3 bugs de Windows (encoding del banner litellm,
> resolución de `claude.CMD`, utf-8 en stdin de subprocess).

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
| **builder** | **CliExecutor** → CLI agéntico según proveedor | **Sí** |

El gate PII se aplica **antes** de elegir backend: la PII nunca llega a un CLI de un
proveedor sin DPA.

> **Verificación pendiente en tu entorno**: claude/codex/aider no están instalados
> aquí, así que la ejecución real está testeada con `subprocess` mockeado. En tu
> máquina, con los CLIs instalados y el proxy levantado, `orchestra cycle` ejecuta
> de verdad. El comando por backend es configurable en `executors.toml` (como el
> `CODEX_CMD` ajustable de dev-config).

**Día 7 — los 5 proveedores + override de tests:**
- ✅ Backend `aider` (`via_proxy`) para deepseek/qwen/gemini — el builder ya cubre **los 5 proveedores**. orchestra inyecta `OPENAI_API_BASE/KEY` del proxy al subprocess de aider; no hay secretos en el argv. **+1 test env + selección.**
- ✅ Override del comando de tests vía `orchestra.toml` del repo (`[tests] command`), con precedencia override > orchestra.toml > autodetección. **+4 tests.**

Builder por proveedor (verificado):

| Proveedor | Backend | Credenciales |
|---|---|---|
| claude | `claude -p ...` | key propia (ANTHROPIC_API_KEY) |
| codex | `codex exec ...` | key propia (OPENAI_API_KEY) |
| deepseek / qwen / gemini | `aider --model openai/{model} ...` | proxy litellm (OPENAI_API_BASE) |

**Día 8 — endurecimiento del runtime:**
- ✅ **Fallback automático** por caída/rate-limit: si un proveedor lanza un error
  transitorio (proxy caído, status≠2xx, CLI no encontrado), el runner reintenta con
  el siguiente de la cadena (`routing.fallback`), **re-aplicando el gate PII** por
  proveedor. Un `success=False` (tests rojos) NO dispara fallback — eso es un FAIL
  normal que evalúa el tester. **+4 tests.**
- ✅ `orchestra config show` — imprime la config resuelta (proveedores+DPA, roles,
  gate PII, backends del builder). **+1 test.**

Demostrado: con `provider=deepseek` y deepseek devolviendo 503, orchestra reintenta
solo y termina en `qwen` (cadena `deepseek → qwen → claude`). El gate PII se re-evalúa
en cada salto, así que un fallback nunca lleva PII a un proveedor sin DPA.

> `config set` se difiere: editar TOML preservando comentarios necesita `tomlkit`
> (no es dependencia aún). De momento se edita `config/*.toml` a mano.

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

**Día 9 — observabilidad:**
- ✅ **Progreso en vivo**: el CLI imprime cada rol según arranca/termina (`> builder ... claude/claude-sonnet-4-6  3.5s · 1.9k tok`), en ASCII (no depende de la codificación de consola).
- ✅ **Métricas**: tokens y latencia por rol propagados (`ExecutionResult.usage` → `RunResult.usage/elapsed_s`); el proxy los rellena, el CLI los muestra.
- ✅ **`files_changed`** en el resumen de `run` (qué tocó el builder, vía `git diff`).
- ✅ Callback `on_event` en `runner` y `cycle` (start/done por rol) — inyectable y testeado.

**Día 10 — traza del builder + coste:**
- ✅ **Coste estimado** por rol/ciclo: `config/pricing.toml` ($/Mtok por modelo) + `core/cost.py`. El CLI muestra `$x.xxxx` por rol (estimado desde tokens en el proxy). **+5 tests.**
- ✅ **Traza del builder + coste real**: el backend `claude_code` usa `--output-format stream-json --verbose`; `core/executors/claude_stream.py` extrae el texto final (hand-off limpio), la **traza de tool-calls** (`Write src/x.py`, `Bash pytest`…), el usage y el **coste real** que reporta Claude. **+8 tests.**
- ✅ El CLI imprime la traza bajo cada rol builder; codex/aider (texto plano) no se parsean (fallback automático).

**Día 11 — streaming en directo:**
- ✅ `_default_run` pasa de `subprocess.run` (bloqueante) a **`Popen` + lectura incremental**: lee el stdout del CLI línea a línea y emite un evento `tool_call` **según llega**. El prompt se escribe a stdin en un hilo (evita deadlock).
- ✅ `Executor.execute` gana `on_event` (el `CliExecutor` lo usa para streaming; el proxy lo ignora). `claude_stream.tool_calls_in_line` parsea cada línea JSONL incrementalmente.
- ✅ El CLI imprime el builder **en directo**: las tool-calls aparecen mientras Claude trabaja, no al terminar. Verificado: con un proceso que gotea, los eventos salen a los 0.0s y 0.4s, no al final.

```
  > builder
      . Write tests/test_slug.py        ← aparece cuando Claude lo hace
      . Write src/slug.py
      . Bash pytest -q
    done claude/claude-sonnet-4-6  78.3s · 1.5k tok · $0.0418
```

**Día 12 — conocimiento del equipo: skills disciplinarias por rol:**
- ✅ Mecanismo `skills = [...]` en `roles.toml`; el `prompt_builder` inyecta el contenido de cada skill al rol que la declara (estático, no auto-discovery — encaja con el modelo agnóstico). **+2 tests.**
- ✅ 4 skills propias de orchestra (concisas, agnósticas, sin maquinaria de Claude Code): `security-review`, `rgpd-review` → **tester**; `self-critique` → **planner**; `systematic-debugging` → **builder`.
- Es el primer trozo de **paridad con dev-config traído "de forma correcta"**: el *conocimiento* (texto) se inyecta a cualquier modelo; el *mecanismo* de auto-discovery de Claude Code no se reinventa.
- ✅ **2 rules portadas**: `60-git-pr` (siempre) y `30-python-playwright` (**condicional al stack** — solo si el repo target tiene `pyproject.toml`/`requirements.txt`). Quedan las 7 rules de dev-config cubiertas salvo `40-session-log`, que no aplica (era de los hooks de Claude Code). **+2 tests.**

> Pendiente de paridad: las skills de flujo interactivo (brainstorming, worktrees…) no aplican al ciclo orquestado; el resto (MCPs, CI, GGA, templates, CLAUDE.md) se traerá vía un futuro `orchestra deploy` que las despliega al repo target. Ver el inventario de paridad.

## Lo que viene

| Hito | Entrega |
|---|---|
| **Engram** | Instalar el binario + cablear el MCP para memoria persistente cross-model. |
| `config set` | Edición de config preservando comentarios (requiere `tomlkit`). |
| **Verificación real** del resto | codex/aider/deepseek/qwen/gemini contra sus CLIs y keys (claude ya verificado end-to-end). |

> El sistema está **funcionalmente completo y verificado con Claude**: 3 roles,
> rotación por rol entre 5 proveedores, gate PII enforced (re-evaluado en cada
> fallback), routing del veredicto, ejecución real delegada a CLIs, fallback
> automático, y observabilidad completa (progreso en vivo, **streaming del builder
> en directo**, métricas, coste estimado+real, traza de tool-calls).

## Requisitos

- Python ≥ 3.11 (usa `tomllib` de stdlib).
- A partir del día 2: `litellm[proxy]`, y las API keys en `.env` (ver `.env.example`).
