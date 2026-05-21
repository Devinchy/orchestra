# Skill: security-review

Al revisar un diff/código, recórrelo con el checklist OWASP Top 10 contextualizado.
Reporta hallazgos por severidad (crítico/alto/medio/bajo). No inventes vulnerabilidades:
si una categoría no aplica, dilo. Mejor 3 hallazgos reales que 10 inventados.

## Checklist

- **A01 Access**: ¿rutas nuevas sin check de permiso server-side? ¿IDOR (IDs sin verificar dueño)?
- **A02 Crypto**: ¿PII/tokens/secretos en logs? ¿hash débil (MD5/SHA1) en vez de bcrypt/argon2? ¿`verify=False`/HTTP plano? Credenciales del usuario (cert, claves privadas) que el código lea/exporte → bloqueante.
- **A03 Injection**: SQL con f-string/concat (debe ser parametrizado). `subprocess(..., shell=True)` con input externo. Path traversal en `set_input_files`/uploads.
- **A04 Diseño**: ¿validación de tamaño en uploads? ¿rate limiting en login/formularios? ¿autorización que confía en input del cliente (`is_admin` en el body)?
- **A05 Config**: debug on, stack traces al usuario, CORS `*`.
- **A06 Deps**: versiones sin pinear, CVEs conocidos, librerías abandonadas.
- **A08 Integridad**: `curl|sh`, `pickle.loads`/`yaml.load` de input externo sin SafeLoader.
- **A09 Logging**: ¿se loggean fallos de auth? ¿sin PII ni secretos en logs?
- **A10 SSRF**: endpoints con URLs del usuario → validar contra IPs internas (127.0.0.1, 169.254.169.254, 10.*).

## Formato de hallazgo

`[severidad] archivo:línea — categoría OWASP — descripción + recomendación concreta`

Si revisas el diff de una tarea, integra el veredicto de seguridad en tu evaluación:
un hallazgo crítico/alto no resuelto es motivo de FAIL.
