# Skill: rgpd-review

Revisa si el cambio trata datos personales de forma que choque con RGPD. No eres
abogado: señalas zonas de riesgo. Si hay duda real, recomienda consulta legal.

## Qué es PII

- **Directos**: DNI/NIE/NIF, nombre completo, email personal, teléfono, dirección, credenciales personales (cert, claves).
- **Indirectos**: CIF, IP, fingerprint, IDs internos cruzables con un identificador directo.
- **Categoría especial (art. 9)**: salud, ideología, religión, biométricos, genéticos. No deberían aparecer; si aparecen → bloqueante.

## Qué revisar

1. **PII en logs** → bloqueante. Nunca DNI/nombre/email, contenido de archivos del usuario, tokens, cookies, headers `Authorization`/`Cookie`. Solo IDs internos + timestamp + código de resultado.
2. **Minimización**: ¿se piden/guardan datos que la función no necesita?
3. **Retención**: ¿hay política de purga? Logs: 30 días, sin PII.
4. **Transferencias**: ¿se envía PII a un endpoint fuera del EEE o a un modelo sin DPA? Datos de cliente solo a proveedores con DPA o modelos open-weights self-hosted.
5. **Derechos**: si se persisten datos del usuario, ¿hay forma de exportar/rectificar/borrar? (En PoC sin backend → N/A, documéntalo.)

## Formato

`[Bloqueante|Atención|OK] archivo:línea — categoría — qué cambiar`

Si no hay tratamiento de PII en el cambio, dilo en una línea. En tests, datos
sintéticos obvios (`00000000A`, fechas `2099-*`).
