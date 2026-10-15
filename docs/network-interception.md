# Intercepción de red (Network Interception)

La verdad matemática (saldo, apuesta, premio) se lee del tráfico del juego con Playwright, a coste 0.
Gemini solo verifica que **el jugador ve** esos mismos valores.

## Flujo

1. `GameFlow` adjunta `NetworkMonitor` a la página **antes** de navegar (captura el `doInit` con el saldo inicial).
2. El listener (`page.on("response")` + `page.on("websocket")`) filtra XHR/fetch cuya URL contiene
   `gameService`, `/spin`, `/balance`, `/result`, `/gs2c/` o cuyo cuerpo trae `action=do…`.
3. `parser.py` convierte `key=value&…` (o JSON plano) en `GameTransaction` con `Decimal`. Bet = `c × l`.
4. Una ronda queda **liquidada** cuando el servidor responde `na=s`. Si hay premio (`na=c`) se espera al `doCollect`.
5. Esa llegada es el disparador de la captura final → **una** llamada a Gemini con las cifras del servidor
   como referencia (`vision/grounding.py`).

## Presupuesto de Gemini por test

| Llamada | Cuándo |
|---|---|
| `locate_spin_button` | 1 vez por mercado (caché) |
| `read_screen_grounded` | 1 vez, sobre la captura al liquidarse la ronda |

(Pro solo si Flash devuelve `legible=false`.)

## Anti-alucinación

- El prompt incluye los valores del servidor **solo como referencia** y prohíbe copiarlos.
- Gemini devuelve texto crudo; la comparación se hace **en código** (`compare_reading`), nunca con un "coincide" dicho por el modelo.
- `GROUNDING_INCLUDE_VALUES=false` fuerza una lectura ciega (sin cifras) si se sospecha sesgo de confirmación.

## Calibración (hacer una vez con tráfico real)

Los nombres de campo (`balance`, `tw`, `c`, `l`, `na`, `fs*`, `error`) están en `FieldMap` y salen del formato
`gs2c` conocido, **sin verificar en vivo**. Tras una ejecución real, revisar
`artifacts/<agent_id>/network/game_transactions.json` (sin cookies ni tokens) y ajustar `FieldMap` si hace falta.
Puntos a confirmar: clave del saldo, si el premio se acredita en el spin o en el collect, cómo responde el
servidor a un giro sin saldo (error explícito vs. el cliente lo bloquea sin tráfico).

## Qué NO cubre

- La prueba de que los rodillos giran visualmente: el detector OpenCV (`motion_detector.py`) no está en esta ruta;
  S1.05/S1.06 se apoyan en el servidor y en el vídeo grabado. Se puede añadir como check extra de coste 0.
- La ruta `live=False` de `SubAgentWorker` sigue siendo la simulada de los tests unitarios; **no usarla para resultados reales**.
