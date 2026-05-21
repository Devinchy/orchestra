# Skill: systematic-debugging

Ante un test que falla o comportamiento inesperado, encuentra la **causa raíz** antes
de tocar nada. Arreglar el síntoma es fallo. Iron Law: ningún fix sin investigación primero.

## Las 4 fases (cada una antes de la siguiente)

1. **Causa raíz** — lee el error entero (no solo la 1ª línea del traceback). Reproduce de forma consistente. Revisa cambios recientes (`git diff`). En sistemas multi-capa, añade instrumentación para ver *dónde* rompe. Traza el flujo del dato hasta su origen. Arregla en el origen, no en el síntoma.
2. **Patrón** — busca código similar que SÍ funciona en el repo. Compara y lista TODAS las diferencias (por pequeñas que parezcan). Si es un patrón conocido, lee la referencia completa, no escanees.
3. **Hipótesis** — una a la vez, escrita: "creo que X es la causa porque Y". Test mínimo que la pruebe. Una variable por iteración.
4. **Fix** — un test que falle primero (reproduce el bug). Un único fix que ataca la causa raíz. Verifica que el test pasa y que no rompiste otros.

## Red flags (para y vuelve a fase 1)

"Fix rápido por ahora", "pruebo a cambiar X a ver", "varios cambios a la vez", "probablemente sea X". Si llevas **3+ fixes fallidos**: para y cuestiona la arquitectura — no añadas un cuarto fix.
