# orchestra — Manual de uso

orchestra orquesta un **ciclo TDD de 3 roles** (planner → builder → tester) y te deja
**elegir qué modelo corre cada rol** (Claude, Codex, DeepSeek, Qwen, Gemini), sin
reescribir nada. El conocimiento del equipo (rules + skills) y la política de modelos
viven en un solo sitio y se aplican en cada ciclo. Es agnóstico del SO y del proveedor.

> Convención de este manual: comandos **Linux/macOS** como principal (`.venv/bin/...`).
> En **Windows + Git Bash**, el venv es `.venv/Scripts/` y hace falta `PYTHONIOENCODING=utf-8`
> al arrancar el proxy. Esas diferencias están marcadas como **[Windows]**.

---

## Mapa mental (cómo encajan las piezas)

```
        TÚ (un repo de producto)
          │  orchestra cycle --slug mi-tarea
          ▼
   ┌──────────────┐   planner/tester (razonan)   ┌─────────────────────┐
   │  orchestra   │ ───────────────────────────► │ proxy litellm (local)│ ──► Anthropic / OpenAI / …
   │ (orquestador)│                               └─────────────────────┘
   │              │   builder (edita el repo)     ┌─────────────────────┐
   │              │ ───────────────────────────► │ CLI agéntico         │ ──► claude / codex / aider
   └──────────────┘                               └─────────────────────┘
```

- **planner** y **tester** razonan → van por el **proxy litellm** (un servicio local).
- **builder** edita el repo de verdad → va por un **CLI agéntico** (`claude`, `codex`, `aider`).

---

## 1. Instalar el framework (una vez por máquina)

### Requisitos
- **Python ≥ 3.11**
- Para el **builder**: el CLI del proveedor que vayas a usar — `claude` (Claude Code),
  `codex` (Codex CLI) y/o `aider`. Instala el/los que necesites y haz login en ellos.
- (Opcional) **API keys** de los proveedores que uses por proxy (planner/tester).

### Instalación
```bash
git clone <repo-orchestra> ~/orchestra && cd ~/orchestra

python -m venv .venv
source .venv/bin/activate            # [Windows] source .venv/Scripts/activate
pip install -e .                      # instala el comando `orchestra`
pip install "litellm[proxy]"          # la capa de modelos (proxy)
```

### Configurar las API keys
```bash
cp .env.example .env
# edita .env y pon SOLO las keys de los proveedores que vayas a usar por proxy:
#   ANTHROPIC_API_KEY=sk-ant-...
#   OPENAI_API_KEY=sk-...
#   LITELLM_MASTER_KEY=sk-local-orchestra   (cualquier string; protege el proxy local)
#   LITELLM_PROXY_URL=http://localhost:4000
```
> ⚠️ La key va en `.env` (gitignored). **Nunca** la pegues en chats ni en `.env.example`.

### Ajustar los IDs de modelo
`litellm.yaml` mapea nombres internos (`claude-sonnet-4-6`) a IDs reales del proveedor.
Revisa que el `model:` de cada entrada sea un ID que tu cuenta tenga (cámbialo si no).

---

## 2. Levantar el proxy (capa de modelos)

El proxy traduce cualquier proveedor a una API común. **Déjalo corriendo** en su terminal:

```bash
source .venv/bin/activate
set -a; source .env; set +a            # carga las keys al entorno
litellm --config litellm.yaml --port 4000
```
**[Windows]**:
```bash
set -a; source .env; set +a
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 ./.venv/Scripts/litellm.exe --config litellm.yaml --port 4000
```
Verás la lista de modelos y `Application startup complete`. No cierres esta terminal.
> Si arranca en un puerto distinto al 4000, ajusta `LITELLM_PROXY_URL` en `.env`.

**Comprobar que un modelo responde** (en otra terminal):
```bash
orchestra config show          # ¿qué modelos/proveedores hay configurados?
# o una llamada directa:
curl -s http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-local-orchestra" -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-6","messages":[{"role":"user","content":"di hola"}],"max_tokens":20}'
```

---

## 3. Preparar tu proyecto

En la raíz del repo donde quieres trabajar:
```bash
cd ~/dev/mi-proyecto
orchestra init
```
Crea `progress/` (artefactos del ciclo, gitignored), `context/`, `PHASE_PLAN.md`, y
`orchestra.toml` (con el comando de tests **autodetectado**). Es idempotente — no pisa
nada existente.

Luego **edita `PHASE_PLAN.md`** con tu objetivo (qué quieres construir en esta fase).

---

## 4. Cheatsheet de comandos

| Comando | Qué hace |
|---|---|
| `orchestra init [path] [--test-command CMD]` | Prepara un repo para orquestar ciclos. |
| `orchestra run <rol> --slug X` | Ejecuta UN rol (`planner`/`builder`/`tester`) sobre la tarea `X`. |
| `orchestra run <rol> --slug X --provider P --model M` | Igual, forzando proveedor/modelo solo para esta corrida. |
| `orchestra cycle --slug X` | Ciclo completo planner→builder→tester con los modelos por defecto. |
| `orchestra cycle --slug X --planner codex --builder claude --tester codex` | Ciclo rotando el modelo por rol. |
| `orchestra cycle --slug X --all codex` | Ciclo con el mismo proveedor en los 3 roles. |
| `orchestra cycle --slug X --max-iters 5` | Tope de vueltas builder↔tester (default 3). |
| `orchestra status` | Muestra la tarea activa del repo actual. |
| `orchestra config show` | Imprime proveedores+DPA, modelos por rol, gate PII, backends del builder. |
| `orchestra config set <clave> <valor>` | Cambia config preservando comentarios. Ej: `config set roles.builder.default_provider codex`. |

> Si no activaste el venv, antepón la ruta: `~/orchestra/.venv/bin/orchestra ...`
> (**[Windows]** `~/orchestra/.venv/Scripts/python.exe -m orchestra.cli ...`).

---

## 5. Flujo de trabajo típico

```bash
# (terminal 1) proxy corriendo  ── ver sección 2

# (terminal 2) en tu repo
orchestra init                       # solo la primera vez
$EDITOR PHASE_PLAN.md                # define el objetivo de la fase

orchestra cycle --slug login-jwt     # planifica → implementa → testea → enruta
```
Verás el progreso en vivo:
```
  > planner
    done claude/claude-opus-4-7  4.1s · 0.6k tok · $0.0218
  > builder
      . Write tests/test_login.py    ← lo que el builder hace, en directo
      . Write src/login.py
      . Bash pytest -q
    done claude/claude-sonnet-4-6  62.8s · $0.0391
  > tester
    done claude/claude-opus-4-7  7.2s · 1.1k tok · $0.0402
==================================================
  veredicto final: PASS
  total:           74.1s · $0.1011
==================================================
```
Los artefactos quedan en `progress/`: `task_<slug>.md`, `builder_<slug>.md`,
`acceptance_<slug>.md`, `transcript_<slug>.md`. El **commit lo haces tú** (orchestra no commitea).

### Si el tester devuelve FAIL
El ciclo **re-itera solo**: vuelve al builder con las instrucciones del tester (o al
planner si el scope estaba mal), hasta PASS o `--max-iters`. No tienes que hacer nada.

---

## 6. Conceptos clave (lo que cuentas al dev nuevo)

- **3 roles fijos**: `planner` (diseña la tarea con criterios de aceptación verificables),
  `builder` (escribe tests + código, TDD), `tester` (re-ejecuta tests, revisa, emite
  veredicto PASS/FAIL + a qué rol volver).
- **Rotación por rol**: el modelo de cada rol es **config**, no código. Patrón recomendado:
  modelo **potente** para planner/tester (razonan), **económico** para builder (ejecuta).
- **Gate PII (automático)**: si una tarea toca datos sensibles y el proveedor del rol no
  tiene DPA, orchestra **rebota** a uno que sí (o avisa, según `pii_gate.mode`). Nunca
  sale PII a un proveedor sin contrato — ni siquiera tras un fallback. Ver `MODEL_POLICY.md`.
- **Conocimiento del equipo**: las `rules/` (siempre) y las `skills/` (por rol:
  security-review/rgpd-review al tester, etc.) se **inyectan** al prompt de cada rol.
- **Observabilidad**: progreso en vivo, streaming de las acciones del builder, tokens,
  coste por rol y total del ciclo.

---

## 7. Configurar / rotar modelos

**Por defecto** (vive en `config/roles.toml`):
```bash
orchestra config set roles.planner.default_model claude-opus-4-7
orchestra config set roles.builder.default_provider codex
```
**Puntual** (solo esa corrida, sin tocar config):
```bash
orchestra run builder --slug X --provider codex --model gpt-5-codex
orchestra cycle --slug X --planner codex --builder claude --tester codex
```
**Qué proveedor/modelo hay** y cómo se ejecuta cada uno:
```bash
orchestra config show
```

---

## 8. Troubleshooting

| Síntoma | Causa / arreglo |
|---|---|
| El proxy aborta al arrancar (**[Windows]**) | Falta `PYTHONIOENCODING=utf-8` (el banner de litellm rompe en cp1252). |
| `model not found` en una llamada | El ID en `litellm.yaml` no existe en tu cuenta — ponlo real. |
| `orchestra run` no conecta al proxy | El proxy no está vivo o está en otro puerto → ajusta `LITELLM_PROXY_URL` en `.env`. |
| Builder: `command not found` / `WinError 2` | El CLI (`claude`/`codex`/`aider`) no está instalado o no en PATH. orchestra resuelve `.CMD` en Windows, pero el binario debe existir. |
| El tester no re-ejecuta tests | Define el comando en `orchestra.toml` (`[tests] command = "..."`) si la autodetección falla. |
| `Veredicto` no parseado | El modelo del tester no siguió el formato — suele pasar con modelos flojos; usa uno más capaz para el tester. |
| Un builder se cuelga | Hay timeout (default 600s); el watchdog lo mata. Ajustable. |

---

## 9. Estado y pendientes

- **Verificado end-to-end con Claude** (proxy + CLI). codex/aider/deepseek/qwen/gemini
  están cableados pero pendientes de verificación real contra sus CLIs/keys.
- **Engram (memoria persistente)**: pendiente. Es un MCP server standalone que corre
  nativo en **Linux** — se instalará y cableará en ese entorno. Hasta entonces, los
  ciclos funcionan sin memoria entre sesiones.

---

## Referencia rápida de archivos

| Archivo | Qué es |
|---|---|
| `config/providers.toml` | Proveedores: modelos, `dpa_signed`, soporte MCP/tools. |
| `config/roles.toml` | Modelo + skills por rol. |
| `config/routing.toml` | Gate PII (modo, fallback) + cadena de fallback. |
| `config/executors.toml` | Qué CLI ejecuta el builder según el proveedor. |
| `config/pricing.toml` | Tarifas $/Mtok para estimar coste. |
| `litellm.yaml` | Config del proxy (model_list + MCP). |
| `MODEL_POLICY.md` | El "porqué" de la política de modelos + proceso de excepción. |
| `<repo>/orchestra.toml` | Config del repo target (comando de tests). |
| `<repo>/PHASE_PLAN.md` | Roadmap por fases del proyecto. |
| `<repo>/progress/` | Artefactos de cada ciclo (gitignored). |
