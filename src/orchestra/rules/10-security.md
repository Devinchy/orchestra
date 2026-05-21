# Reglas de seguridad

> Aplican a cambios que tocan auth, manejo de archivos, integraciones externas o datos del usuario.

## No negociables
1. **Secretos nunca en código.** Variables de entorno / secret manager. Nada de `api_key = "sk-..."`.
2. **Credenciales del usuario** (cert digital, claves privadas, OAuth refresh tokens): el código nunca las lee, exporta ni envía.
3. **Logs nunca con PII** ni secretos. Solo IDs internos, timestamps, códigos de resultado.
4. **`subprocess` con `shell=True` e input externo**: prohibido.

## OWASP — checklist mental
- A01 Access: ¿toda ruta nueva valida permiso server-side?
- A02 Crypto: ¿bcrypt/argon2, no MD5/SHA1? ¿TLS sin `verify=False`?
- A03 Injection: ¿queries parametrizadas, no f-strings con input?
- A04 Diseño: ¿validación de tamaño en uploads, rate limiting donde aplica?
- A08 Integridad: ¿sin `curl | sh`, sin deserializar input externo sin validar?
- A09 Logging: ¿se loggean fallos de auth sin PII?
- A10 SSRF: ¿endpoints con URLs del usuario validan contra IPs internas?
