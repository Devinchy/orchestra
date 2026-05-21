# Política de modelos — orchestra

> **El "porqué" y el proceso humano.** El "qué" (qué proveedor, qué DPA, qué gate)
> vive en `config/` y **el sistema lo aplica solo** en cada llamada. Este documento
> no duplica esa configuración: explica la intención y cómo cambiarla.
>
> - **Estado vigente** (qué hay activo ahora): `orchestra config show`
> - **Implementación** (la verdad ejecutable): `config/providers.toml`, `config/routing.toml`, `config/roles.toml`
> - **Por qué + proceso**: este archivo

## Principio

orchestra rota frontier models por rol. Esa libertad tiene un límite **no negociable**:
los datos personales reales del cliente no pueden salir a un proveedor sin contrato
que los proteja. A diferencia de una política en prosa que esperas que la gente
respete, aquí la regla **se enforcea automáticamente** (ver "Cómo se aplica").

## Regla dura de PII

Si una tarea procesa **PII real** (DNI, nombres, emails, contenido de archivos del
usuario, datos de empleados, registros médicos…), el modelo que la vea **debe** ser:

| Clase de proveedor | `dpa_signed` | ¿Puede ver PII real? |
|---|---|---|
| Con DPA firmado por la organización (p. ej. Anthropic) | `true` | **Sí** |
| Open-weights self-hosted (p. ej. Qwen vía Ollama) | `"self_hosted"` | **Sí** (no sale de tu máquina) |
| Endpoint público sin DPA específico | `false` | **No** |

"Sin DPA" incluye por defecto los endpoints públicos de cualquier proveedor del que
la organización no haya firmado un DPA — da igual el país o la marca. El default es
"no", y se sube a "sí" solo con un DPA real (ver "Proceso de excepción").

## Cómo se aplica (automático, no confías en la memoria de nadie)

1. `core/pii.py` decide si una tarea **toca PII** (paths sensibles del task file).
2. `core/routing.py` aplica el **gate**: si toca PII y el proveedor del rol no puede
   verla (`dpa_signed=false`), con `pii_gate.mode = "strict"` **rebota** al
   `strict_fallback` (un proveedor con DPA o self-hosted). El gate se re-evalúa en
   **cada salto de fallback**, así que una caída de proveedor nunca lleva PII a un
   destino sin DPA.
3. El modo (`strict` / `advisory`) y el fallback viven en `config/routing.toml`.

Con datos **sintéticos obvios** (NIFs `00000000A`, fechas `2099-*`, textos de prueba)
no hay PII real: cualquier proveedor vale. Mantén el gate en `advisory` solo si
asumes esa responsabilidad; en duda, `strict`.

## Proceso de excepción (autorizar un proveedor para PII)

Para que un proveedor pase a poder ver PII real:

1. Consigue un **DPA firmado** por la organización con ese proveedor.
2. En `config/providers.toml`, pon `dpa_signed = true` (o `"self_hosted"` si es local).
3. Si va a ser destino de rebote del gate, ajústalo en `config/routing.toml`
   (`pii_gate.strict_fallback`).
4. **PR** con: caso de uso, proveedor, tipo de datos que vería, referencia al DPA,
   y un **owner** que se responsabilice de retirarlo si el caso de uso desaparece.
5. Aprobación: 1 dev del equipo + checkbox de "he leído y acepto el riesgo".

Quitar un proveedor es lo contrario: `dpa_signed = false` (vuelve a quedar fuera de
PII automáticamente).

## Modelo por rol (rotación con criterio)

La asignación rol→modelo vive en `config/roles.toml`. Criterio del equipo:

- **Razonamiento** (planner, tester): modelo potente (p. ej. Opus). Diseñar tareas
  con CAs verificables y revisar código exige juicio fino.
- **Ejecución** (builder): modelo económico (p. ej. Sonnet) o el CLI agéntico que
  edita el repo.

> Rotar modelos **no significa** usar uno distinto por capricho en cada corrida. La
> rotación es una herramienta (coste, calidad, redundancia), no caos. El contrato
> común es la tarea + los tests; el modelo es una decisión con criterio.

## Histórico

| Fecha | Cambio | Owner |
|---|---|---|
| (inicial) | Política portada de dev-config al modelo ejecutable de orchestra: la regla vive en `config/` y se enforcea en `routing.py`; este doc cubre el porqué y el proceso. | — |
