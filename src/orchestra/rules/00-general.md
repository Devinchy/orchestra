# Reglas generales

## Cómo trabajamos
- Spec-Driven para features no triviales: spec → plan → tasks antes de código.
- PRs siempre, nunca push directo a `main`.
- ADRs para decisiones de arquitectura: `docs/adr/NNN-titulo.md`.

## Estilo
- Código claro > código corto. Nombres explícitos.
- Comentarios para el "por qué" no obvio, no para lo obvio.
- Tipado estricto donde el lenguaje lo permita.
- Sin abstracciones prematuras: 3 líneas iguales se toleran; un decorador genérico para 2 casos no.

## Lo que NO queremos
- Suprimir warnings sin explicar por qué.
- Commits "fix typo" acumulados — squash antes de mergear.
- Arreglar deuda adyacente "de paso": señálala, no la toques sin pedir.

## Honestidad
- Si no estás seguro, dilo. "No sé, mira X" > alucinación segura.
- Si un fix toca > 100 líneas, expón el plan antes.
