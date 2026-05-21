# Reglas de testing

## Iron Law: TDD estricto
```
NINGÚN CÓDIGO DE PRODUCCIÓN SIN UN TEST QUE FALLA PRIMERO
```
Ciclo RED → GREEN → REFACTOR. Si encuentras código escrito antes que su test, bórralo y empieza por el test.

## Excepciones (limitadas, explícitas)
1. Scripts de bootstrap/setup únicos.
2. Prototipos marcados `# PROTOTYPE` (vida ≤ 1 sprint).
3. Hotfix de incidente activo (test obligatorio antes de cerrar el ticket).
4. DTOs / dataclasses puros sin lógica.
5. Cambios de config.

Fuera de eso, sin excepciones. "Es trivial" / "ya lo probé a mano" / "lo testo después" NO valen.

## No negociables
- **Sin mocks de BD** en tests de integración. BD real en Docker/testcontainer.
- **Un test = una idea.** Sin `if/else` en el cuerpo del test.
- **Nombres descriptivos**: `test_rechaza_xml_mayor_5mb`, no `test_upload_2`.
- **Testea comportamiento, no implementación.** Si el test se rompe al refactor sin cambio funcional, está mal escrito.

## Pirámide
- Unit (mayoría): funciones puras, rápidos.
- Integration: BD/API real, un componente a la vez.
- E2E (pocos): flujos críticos.
