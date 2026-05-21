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

## Estado: días 1–4 completados

Construido **test-first** (la propia filosofía que orquesta). **81 tests verdes.**

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

## ⚠️ Límite actual: orquestación documental, no tool-execution

orchestra **compone prompts, invoca modelos y enruta**. NO ejecuta tool-calls — es
decir, los modelos **no editan el repo directamente**. El "output" de cada rol (su
razonamiento + código/veredicto como texto) se vuelca a su artefacto en `progress/`,
y el siguiente rol lo lee. Es el modelo "architect" (razonar) sin el "editor" (aplicar).

Para que el builder edite código real en disco hace falta un **agent loop con
ejecución de herramientas** (function-calling/MCP + file ops + bash sandbox) — un
hito mayor. Dos caminos posibles, a decidir:
1. **Construir el executor** dentro de orchestra (MCP client + aplicar diffs + correr tests).
2. **Delegar la ejecución** a Claude Code / Codex CLI por rol, usando orchestra solo
   como capa de orquestación + routing + gate PII.

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

## Lo que viene (día 5+)

| Hito | Entrega |
|---|---|
| 5 | Fallback en runtime por caída/rate-limit (`next_fallback` ya existe, falta cablearlo en el invoker con reintento). Pulido del CLI (`config show/set`). Verificación contra el proxy real con Claude + Codex. |
| 6+ | **Decisión grande**: tool-execution (ver "Límite actual"). Construir el agent loop dentro de orchestra, o delegar la ejecución a Claude Code/Codex por rol. |

> El ciclo de orquestación completo (3 roles, rotación de modelos, gate PII, routing
> del veredicto) ya funciona end-to-end. Lo que falta para que sea un agente que
> *modifica el repo* es la capa de ejecución de herramientas.

## Requisitos

- Python ≥ 3.11 (usa `tomllib` de stdlib).
- A partir del día 2: `litellm[proxy]`, y las API keys en `.env` (ver `.env.example`).
