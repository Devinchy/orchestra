# Reglas git y PRs

> Convenciones del equipo para el código que se produce, aunque el commit/PR lo haga
> el humano después del ciclo.

## Branches

- Nunca push directo a `main`. Branch por feature/fix: `feat/upload-validation`, `fix/session-timeout`, `chore/bump-deps`.

## Commits

- Mensaje en **imperativo**: "add upload validation", no "added"/"adding".
- Cuerpo opcional explicando el **por qué**, no el qué.
- Squash antes de mergear (el repo no necesita ver "fix typo" × 8).
- **Nunca** `--no-verify` para saltarse hooks. Si un hook falla, arregla la causa.

## Pull Requests

- Tamaño objetivo: **< 400 líneas** de diff (excluyendo lockfiles/generados). Si supera, dividir.
- Descripción: qué cambia, por qué, cómo se prueba, ¿security-sensitive?

## En el código que generes

- Sin código comentado dejado por olvido (bloques `# old code`, `// TODO remove`).
- Sin `Co-Authored-By` de IA en los mensajes de commit que sugieras.
