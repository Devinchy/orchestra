# Reglas Python + Playwright

> Aplica solo cuando el repo usa Python o Playwright.

## Estilo Python

- Type hints estrictos (`mypy --strict` o `pyright strict`). Sin `Any` salvo justificación con comentario.
- `pathlib.Path` > `os.path`. `dataclass`/`pydantic` > dicts sueltos para datos estructurados.
- Funciones puras donde se pueda; side effects explícitos en el nombre (`save_x`, `submit_y`).
- `from __future__ import annotations` en archivos con muchos hints.

## Playwright

- **Selectores**, por preferencia: `get_by_role` > `get_by_test_id` > `get_by_text`. Evitar XPath/CSS frágiles.
- **Esperas**: `expect(locator).to_be_visible(timeout=...)`. **Nunca** `time.sleep` para "esperar a que cargue".
- **Perfiles persistentes** del navegador (cookies de sesión) → siempre en `.gitignore`.
- **Cierre limpio**: `context.close()`/`browser.close()` en `finally` o con `with`.
- **Credenciales del usuario**: el código nunca las lee/exporta; las consume el navegador del almacén del SO.

## Errores

- No silenciar excepciones (`except: pass`) sin comentario que explique por qué.
- Re-raise con contexto: `raise UploadError("...") from e`.

## Prohibido

- `subprocess.run(..., shell=True)` con input externo.
- Paths Windows hardcoded (`C:\\Users\\...`) — usa `Path.home()` / env vars.
