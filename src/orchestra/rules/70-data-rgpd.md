# Reglas de datos / RGPD

> Versión preventiva: qué evitar mientras escribes código que toca datos personales.

## Qué es PII
- **Directos**: DNI/NIE/NIF, nombre completo, email personal, teléfono, dirección, credenciales personales.
- **Indirectos**: CIF, IP, fingerprint, IDs internos cruzables con un identificador directo.
- **Categoría especial (art. 9)**: salud, ideología, religión, biométricos. No deberían aparecer; si aparecen, bloqueante.

## Qué NO logear
- DNI, nombre, email del usuario.
- Contenido de archivos del usuario.
- Tokens, claves, hashes de password, cookies de sesión.
- Headers `Authorization` / `Cookie`.

## Qué SÍ logear
- ID interno de operación (UUID propio), timestamp, código de resultado (`success`, `validation_error`).

## En código
- Variables: `internal_id` > `dni`. Marca campos PII (`SecretStr` o anotación).
- Nunca `print(usuario)` / `print(request.body)`, ni en debug.
- En tests, datos sintéticos obvios (`00000000A`, fechas `2099-*`).

## Transferencias / modelos
- Datos de cliente solo a proveedores con DPA firmado o modelos open-weights self-hosted.
- El gate PII de orchestra (`routing.toml` + `core/pii.py`) enforza esto automáticamente.
